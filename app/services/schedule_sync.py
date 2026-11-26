"""Centralized transactional scheduling, participant synchronization, and role-locking services."""

from datetime import datetime
from sqlalchemy import func, text, inspect
from sqlalchemy.exc import IntegrityError
from app import db
from app.constants import (
    DESIGNATED_POSITION_KEYS,
    DESIGNATED_POSITION_LABELS,
    UNIQUE_ROLES_LOWER,
    role_to_position_key,
)
from app.models.schedule import MeetingParticipant, ScheduleAuditLog, ScheduleEntry
from app.models.user import User


def get_occupied_unique_roles(exclude_user_id: int | None = None) -> dict[str, User]:
    """Return mapping of lowercase unique role name -> active User holding that role."""
    query = User.query.filter(
        User.is_active.is_(True),
        func.lower(User.role).in_(UNIQUE_ROLES_LOWER),
    )
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return {u.role.strip().lower(): u for u in query.all() if u.role}


def is_role_available(role_name: str, exclude_user_id: int | None = None) -> bool:
    """Return True if role_name can be assigned to an active account."""
    normalized = (role_name or '').strip().lower()
    if normalized not in UNIQUE_ROLES_LOWER:
        return True
    occupied = get_occupied_unique_roles(exclude_user_id=exclude_user_id)
    return normalized not in occupied


def resolve_active_user_for_position(position_key: str) -> User | None:
    """Find the active User account currently holding the given designated position."""
    if not position_key:
        return None
    active_users = User.query.filter(User.is_active.is_(True)).order_by(User.id.asc()).all()
    for u in active_users:
        if role_to_position_key(u.role) == position_key:
            return u
    return None


def get_position_holders_map() -> dict[str, User | None]:
    """Return mapping of each designated position key to its active User (or None)."""
    holders = {key: None for key in DESIGNATED_POSITION_KEYS}
    active_users = User.query.filter(User.is_active.is_(True)).order_by(User.id.asc()).all()
    for u in active_users:
        pos = role_to_position_key(u.role)
        if pos and holders[pos] is None:
            holders[pos] = u
    return holders


def relink_position_participants_for_user(user: User) -> None:
    """When a user becomes the active holder of a designated role, link unassigned position rows."""
    if not user or not user.is_active:
        return
    pos_key = role_to_position_key(user.role)
    if not pos_key:
        return

    rows = MeetingParticipant.query.filter(
        MeetingParticipant.position_key == pos_key
    ).all()
    for row in rows:
        existing_same_user = MeetingParticipant.query.filter(
            MeetingParticipant.schedule_entry_id == row.schedule_entry_id,
            MeetingParticipant.user_id == user.id,
            MeetingParticipant.id != row.id,
        ).first()
        if existing_same_user:
            # Merge standalone user participant row into the position row
            db.session.delete(existing_same_user)
            db.session.flush()
        if row.user_id != user.id:
            row.user_id = user.id
        if row.schedule_entry and user not in row.schedule_entry.attendants:
            row.schedule_entry.attendants.append(user)


def unlink_user_from_position_participants(user: User, old_role: str | None = None) -> None:
    """When a user is deactivated or reassigned away from a designated role, clear user_id on position rows."""
    if not user:
        return
    pos_key = role_to_position_key(old_role if old_role is not None else user.role)
    if not pos_key:
        return
    rows = MeetingParticipant.query.filter(
        MeetingParticipant.position_key == pos_key,
        MeetingParticipant.user_id == user.id,
    ).all()
    for row in rows:
        row.user_id = None
        if row.schedule_entry and user in row.schedule_entry.attendants:
            row.schedule_entry.attendants.remove(user)


def sync_meeting_participants(
    entry: ScheduleEntry,
    position_keys: list[str] | set[str],
    user_ids: list[int] | set[int],
    actor_user: User | None = None,
    action: str = 'updated',
) -> None:
    """
    Synchronize MeetingParticipant rows and legacy schedule_attendants for a ScheduleEntry.
    Deduplicates participants, enforces single-row-per-position and single-row-per-user,
    updates backward-compatible schedule_type, and writes a ScheduleAuditLog entry.
    Caller controls the outer DB transaction.
    """
    valid_positions = []
    seen_pos = set()
    for raw_pos in (position_keys or []):
        key = (raw_pos or '').strip().lower()
        if key in DESIGNATED_POSITION_LABELS and key not in seen_pos:
            seen_pos.add(key)
            valid_positions.append(key)

    parsed_user_ids = []
    seen_uids = set()
    for raw_uid in (user_ids or []):
        try:
            uid = int(raw_uid)
        except (TypeError, ValueError):
            continue
        if uid not in seen_uids:
            seen_uids.add(uid)
            parsed_user_ids.append(uid)

    holders_map = get_position_holders_map()

    # Map each selected position to its current active user (if any)
    desired_pos_to_uid: dict[str, int | None] = {}
    position_paired_uids: set[int] = set()
    for pos_key in valid_positions:
        holder = holders_map.get(pos_key)
        uid = holder.id if holder else None
        desired_pos_to_uid[pos_key] = uid
        if uid is not None:
            position_paired_uids.add(uid)

    # Extra standalone users not already paired with a selected designated position
    desired_extra_uids: set[int] = set()
    if parsed_user_ids:
        existing_users = User.query.filter(User.id.in_(parsed_user_ids)).all()
        valid_uid_set = {u.id for u in existing_users}
        for uid in parsed_user_ids:
            if uid in valid_uid_set and uid not in position_paired_uids:
                desired_extra_uids.add(uid)

    # Flush entry so entry.id is guaranteed to exist
    db.session.flush()

    existing_rows = MeetingParticipant.query.filter_by(schedule_entry_id=entry.id).all()
    existing_by_pos = {r.position_key: r for r in existing_rows if r.position_key}
    existing_extra_by_uid = {
        r.user_id: r for r in existing_rows if not r.position_key and r.user_id is not None
    }

    # Remove stale rows first to avoid unique index collisions on (schedule_entry_id, user_id)
    for pos_key, row in list(existing_by_pos.items()):
        if pos_key not in desired_pos_to_uid:
            db.session.delete(row)
    for uid, row in list(existing_extra_by_uid.items()):
        if uid not in desired_extra_uids or uid in position_paired_uids:
            db.session.delete(row)
    db.session.flush()

    # Upsert designated position rows
    for pos_key in valid_positions:
        uid = desired_pos_to_uid[pos_key]
        row = existing_by_pos.get(pos_key)
        if row:
            if row.user_id != uid:
                row.user_id = uid
        else:
            db.session.add(
                MeetingParticipant(
                    schedule_entry_id=entry.id,
                    position_key=pos_key,
                    user_id=uid,
                )
            )

    # Insert standalone user rows
    for uid in sorted(desired_extra_uids):
        if uid not in existing_extra_by_uid:
            db.session.add(
                MeetingParticipant(
                    schedule_entry_id=entry.id,
                    position_key=None,
                    user_id=uid,
                )
            )

    db.session.flush()

    # Keep legacy schedule_attendants synchronized with all participant user_ids
    all_participant_uids = position_paired_uids | desired_extra_uids
    if all_participant_uids:
        entry.attendants = User.query.filter(User.id.in_(all_participant_uids)).all()
    else:
        entry.attendants = []

    # Update legacy schedule_type for backward compatibility
    if set(valid_positions) == {'proprietor'}:
        entry.schedule_type = 'proprietor'
    elif set(valid_positions) == {'ceo'}:
        entry.schedule_type = 'ceo'
    elif valid_positions:
        entry.schedule_type = 'multi'
    elif entry.user_id is not None:
        entry.schedule_type = 'employee'

    # Audit log
    pos_names = [DESIGNATED_POSITION_LABELS[k] for k in valid_positions]
    extra_names = [
        u.name for u in User.query.filter(User.id.in_(desired_extra_uids)).order_by(User.name.asc()).all()
    ] if desired_extra_uids else []
    participant_summary = ', '.join(pos_names + extra_names) or 'None'

    entry.updated_at = datetime.utcnow()
    if actor_user:
        entry.updated_by_id = actor_user.id

    db.session.add(
        ScheduleAuditLog(
            schedule_entry_id=entry.id,
            entry_snapshot_title=entry.activity,
            actor_id=actor_user.id if actor_user else None,
            action=action,
            details=f"Date: {entry.event_date}, Time: {entry.time}, Participants: [{participant_summary}]",
        )
    )


def toggle_entry_participant_user(entry: ScheduleEntry, target_user: User, actor_user: User | None = None) -> tuple[str, list[dict]]:
    """Toggle a registered User as a participant on entry in a single transaction."""
    existing_user_rows = MeetingParticipant.query.filter(
        MeetingParticipant.schedule_entry_id == entry.id,
        MeetingParticipant.user_id == target_user.id,
    ).all()
    pos_key = role_to_position_key(target_user.role)
    existing_pos_row = (
        MeetingParticipant.query.filter_by(schedule_entry_id=entry.id, position_key=pos_key).first()
        if pos_key
        else None
    )

    if existing_user_rows or existing_pos_row:
        for row in existing_user_rows:
            db.session.delete(row)
        if existing_pos_row and existing_pos_row not in existing_user_rows:
            db.session.delete(existing_pos_row)
        if target_user in entry.attendants:
            entry.attendants.remove(target_user)
        action = 'removed'
    else:
        db.session.add(
            MeetingParticipant(
                schedule_entry_id=entry.id,
                position_key=pos_key,
                user_id=target_user.id,
            )
        )
        if target_user not in entry.attendants:
            entry.attendants.append(target_user)
        action = 'added'

    if actor_user:
        entry.updated_by_id = actor_user.id
    entry.updated_at = datetime.utcnow()
    db.session.add(
        ScheduleAuditLog(
            schedule_entry_id=entry.id,
            entry_snapshot_title=entry.activity,
            actor_id=actor_user.id if actor_user else None,
            action=f"participant_{action}",
            details=f"User {target_user.name} ({target_user.role}) {action}",
        )
    )
    db.session.flush()
    db.session.refresh(entry)
    return action, entry.display_participants()


def toggle_entry_position(entry: ScheduleEntry, position_key: str, actor_user: User | None = None) -> tuple[str, list[dict]]:
    """Toggle a designated position on entry in a single transaction."""
    pos_key = (position_key or '').strip().lower()
    if pos_key not in DESIGNATED_POSITION_LABELS:
        raise ValueError(f"Unknown position key: {position_key}")

    existing_pos_row = MeetingParticipant.query.filter_by(
        schedule_entry_id=entry.id,
        position_key=pos_key,
    ).first()

    if existing_pos_row:
        if existing_pos_row.user and existing_pos_row.user in entry.attendants:
            entry.attendants.remove(existing_pos_row.user)
        db.session.delete(existing_pos_row)
        action = 'removed'
    else:
        holder = resolve_active_user_for_position(pos_key)
        if holder:
            # Remove any duplicate standalone user row before pairing with position_key
            standalone = MeetingParticipant.query.filter_by(
                schedule_entry_id=entry.id,
                user_id=holder.id,
            ).first()
            if standalone:
                db.session.delete(standalone)
                db.session.flush()
            if holder not in entry.attendants:
                entry.attendants.append(holder)
        db.session.add(
            MeetingParticipant(
                schedule_entry_id=entry.id,
                position_key=pos_key,
                user_id=holder.id if holder else None,
            )
        )
        action = 'added'

    if actor_user:
        entry.updated_by_id = actor_user.id
    entry.updated_at = datetime.utcnow()
    db.session.add(
        ScheduleAuditLog(
            schedule_entry_id=entry.id,
            entry_snapshot_title=entry.activity,
            actor_id=actor_user.id if actor_user else None,
            action=f"position_{action}",
            details=f"Position {DESIGNATED_POSITION_LABELS[pos_key]} {action}",
        )
    )
    db.session.flush()
    db.session.refresh(entry)
    return action, entry.display_participants()


def get_schedule_state_version() -> str:
    """Return a lightweight version string reflecting latest schedule/participant changes."""
    latest_entry = db.session.query(
        func.count(ScheduleEntry.id),
        func.max(ScheduleEntry.id),
        func.max(ScheduleEntry.updated_at),
    ).first()
    latest_part = db.session.query(
        func.count(MeetingParticipant.id),
        func.max(MeetingParticipant.id),
    ).first()
    return f"{latest_entry[0]}:{latest_entry[1]}:{latest_entry[2]}|{latest_part[0]}:{latest_part[1]}"


def ensure_schema_and_backfill() -> None:
    """
    Idempotently apply schema additions, database-level partial unique indexes,
    performance indexes, and safe backfill of legacy records without touching existing data.
    Works on both PostgreSQL and SQLite.
    """
    db.create_all()
    dialect = db.engine.dialect.name
    true_lit = 'TRUE' if dialect == 'postgresql' else '1'

    try:
        inspector = inspect(db.engine)

        # 1. request_message columns
        if inspector.has_table('request_message'):
            cols = {c['name'] for c in inspector.get_columns('request_message')}
            modified = False
            if 'feedback_time' not in cols:
                db.session.execute(text('ALTER TABLE request_message ADD COLUMN feedback_time TEXT'))
                modified = True
            if 'feedback_message' not in cols:
                db.session.execute(text('ALTER TABLE request_message ADD COLUMN feedback_message TEXT'))
                modified = True
            if modified:
                db.session.commit()

        # 2. schedule_entry columns
        if inspector.has_table('schedule_entry'):
            cols = {c['name'] for c in inspector.get_columns('schedule_entry')}
            alter_defs = [
                ('given_time', 'TEXT'),
                ('user_id', 'INTEGER'),
                ('google_location', 'TEXT'),
                ('schedule_type', "VARCHAR(40) DEFAULT 'ceo'"),
                ('alert_sent_10m', f'BOOLEAN DEFAULT { "FALSE" if dialect == "postgresql" else "0" }'),
                ('description', 'TEXT'),
                ('meeting_type', "VARCHAR(60) DEFAULT 'Meeting'"),
                ('notes', 'TEXT'),
                ('created_by_id', 'INTEGER'),
                ('updated_by_id', 'INTEGER'),
                ('updated_at', 'TIMESTAMP' if dialect == 'postgresql' else 'DATETIME'),
            ]
            modified = False
            for col_name, col_type in alter_defs:
                if col_name not in cols:
                    db.session.execute(text(f'ALTER TABLE schedule_entry ADD COLUMN {col_name} {col_type}'))
                    modified = True
            if modified:
                db.session.commit()

        # 3. user columns (must quote "user" for PostgreSQL compatibility)
        if inspector.has_table('user'):
            cols = {c['name'] for c in inspector.get_columns('user')}
            modified = False
            if 'phone_number' not in cols:
                db.session.execute(text('ALTER TABLE "user" ADD COLUMN phone_number VARCHAR(20)'))
                modified = True
            if 'is_active' not in cols:
                db.session.execute(text(f'ALTER TABLE "user" ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT {true_lit}'))
                modified = True
            if modified:
                db.session.commit()

        # 4. notification columns
        if inspector.has_table('notification'):
            cols = {c['name'] for c in inspector.get_columns('notification')}
            if 'schedule_entry_id' not in cols:
                db.session.execute(text('ALTER TABLE notification ADD COLUMN schedule_entry_id INTEGER'))
                db.session.commit()

        # 5. Indexes & Database-level Uniqueness Constraints
        index_statements = [
            'CREATE INDEX IF NOT EXISTS ix_schedule_entry_event_date ON schedule_entry (event_date)',
            'CREATE INDEX IF NOT EXISTS ix_schedule_entry_user_id ON schedule_entry (user_id)',
            'CREATE INDEX IF NOT EXISTS ix_schedule_entry_status ON schedule_entry (status)',
            'CREATE INDEX IF NOT EXISTS ix_schedule_entry_created_by_id ON schedule_entry (created_by_id)',
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_mp_entry_position ON meeting_participant (schedule_entry_id, position_key) WHERE position_key IS NOT NULL',
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_mp_entry_user ON meeting_participant (schedule_entry_id, user_id) WHERE user_id IS NOT NULL',
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_user_active_new_unique_role ON \"user\" (LOWER(role)) WHERE is_active = {true_lit} AND LOWER(role) IN ('agm', 'operation manager', 'admin in charge', 'hr manager')",
        ]
        for stmt in index_statements:
            db.session.execute(text(stmt))
        db.session.commit()

        # Also enforce DB-level uniqueness on Admin & Proprietor if existing data has no duplicates
        dup_check = db.session.execute(
            text(
                f"SELECT LOWER(role), COUNT(*) FROM \"user\" "
                f"WHERE is_active = {true_lit} AND LOWER(role) IN ('admin', 'proprietor') "
                f"GROUP BY LOWER(role) HAVING COUNT(*) > 1"
            )
        ).fetchall()
        if not dup_check:
            db.session.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS uq_user_active_admin_proprietor "
                    f"ON \"user\" (LOWER(role)) "
                    f"WHERE is_active = {true_lit} AND LOWER(role) IN ('admin', 'proprietor')"
                )
            )
            db.session.commit()

        # 6. Safe, idempotent backfill of legacy schedule_entry records
        proprietor_user = resolve_active_user_for_position('proprietor')
        ceo_user = resolve_active_user_for_position('ceo')

        # Backfill created_by_id for legacy employee records if unset
        legacy_entries = ScheduleEntry.query.all()
        backfilled_count = 0
        for entry in legacy_entries:
            if entry.created_by_id is None and entry.user_id is not None:
                entry.created_by_id = entry.user_id

            if not entry.participants:
                # Only backfill entries that do not yet have MeetingParticipant rows
                is_prop = entry.schedule_type == 'proprietor' or (
                    proprietor_user is not None and entry.user_id == proprietor_user.id
                )
                is_ceo = (entry.schedule_type in ('ceo', None)) and entry.user_id is None

                if is_prop:
                    db.session.add(
                        MeetingParticipant(
                            schedule_entry_id=entry.id,
                            position_key='proprietor',
                            user_id=proprietor_user.id if proprietor_user else None,
                        )
                    )
                    backfilled_count += 1
                elif is_ceo:
                    db.session.add(
                        MeetingParticipant(
                            schedule_entry_id=entry.id,
                            position_key='ceo',
                            user_id=ceo_user.id if ceo_user else None,
                        )
                    )
                    backfilled_count += 1

                # Preserve legacy attendants as user-level participants without corrupting role calendars
                existing_paired_uid = (
                    proprietor_user.id if (is_prop and proprietor_user)
                    else (ceo_user.id if (is_ceo and ceo_user) else None)
                )
                for att in entry.attendants:
                    if att.id == existing_paired_uid:
                        continue
                    db.session.add(
                        MeetingParticipant(
                            schedule_entry_id=entry.id,
                            position_key=None,
                            user_id=att.id,
                        )
                    )

        if backfilled_count:
            db.session.commit()
        else:
            db.session.commit()
    except IntegrityError as ie:
        db.session.rollback()
        print("Schema migration integrity warning:", ie)
    except Exception as e:
        db.session.rollback()
        print("Schema verification warning:", e)
