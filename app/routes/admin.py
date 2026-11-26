from datetime import datetime, date
from flask import Blueprint, request, redirect, url_for, session, flash, render_template
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app import db
from app.constants import (
    ALLOWED_REGISTRATION_ROLES,
    DESIGNATED_POSITIONS,
    DESIGNATED_POSITION_LABELS,
)
from app.models.schedule import ScheduleEntry, ScheduleAuditLog
from app.models.user import User
from app.services.schedule_sync import (
    get_occupied_unique_roles,
    get_position_holders_map,
    is_role_available,
    relink_position_participants_for_user,
    sync_meeting_participants,
    unlink_user_from_position_participants,
)

admin_bp = Blueprint('admin', __name__)

_CANONICAL_ROLE_MAP = {r.lower(): r for r in ALLOWED_REGISTRATION_ROLES}


def parse_event_date(raw_value):
    if raw_value is None or raw_value == '':
        return date.today()
    if isinstance(raw_value, date) and not isinstance(raw_value, datetime):
        return raw_value
    if isinstance(raw_value, datetime):
        return raw_value.date()
    try:
        return datetime.strptime(raw_value, '%Y-%m-%d').date()
    except ValueError:
        return date.fromisoformat(raw_value)


def build_time_range(form, fallback=''):
    start_time = form.get('start_hour', '').strip()
    start_minute = form.get('start_minute', '').strip()
    start_meridiem = form.get('start_meridiem', '').strip()
    end_time = form.get('end_hour', '').strip()
    end_minute = form.get('end_minute', '').strip()
    end_meridiem = form.get('end_meridiem', '').strip()
    start_value = f"{start_time}:{start_minute} {start_meridiem}" if start_time and start_minute else ''
    end_value = f"{end_time}:{end_minute} {end_meridiem}" if end_time and end_minute else ''
    if start_value and end_value:
        return f"{start_value} - {end_value}"
    return start_value or end_value or fallback


def split_time_for_form(time_str):
    start_time, end_time = '', ''
    if time_str:
        parts = [part.strip() for part in time_str.split('-')]
        if len(parts) >= 2:
            start_time, end_time = parts[0], parts[1]
        else:
            start_time = parts[0]

    def _unpack(val):
        if val and ':' in val:
            try:
                time_part, meridiem_part = val.split()
                h, m = time_part.split(':')
                return h, m, meridiem_part
            except Exception:
                pass
        return '', '', ''

    sh, sm, smer = _unpack(start_time)
    eh, em, emer = _unpack(end_time)
    return sh, sm, smer, eh, em, emer


def schedule_manage_required(view):
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_active or not user.can_create_meetings():
            flash('Only authorized staff or designated role holders can manage meetings.', 'danger')
            return redirect(url_for('dashboard.schedule'))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


def admin_required(view):
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_active or not user.is_admin_role():
            flash('Only Personal Assistant, Senior Assistant, or Admin can perform this action.', 'danger')
            return redirect(url_for('dashboard.schedule'))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


def admin_only(view):
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_active or user.role != 'Admin':
            flash('Only the Admin can manage users.', 'danger')
            return redirect(url_for('dashboard.schedule'))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


def _resolve_initial_positions(current_user, target):
    if target == 'combined':
        return [key for key, _ in DESIGNATED_POSITIONS]
    if target in DESIGNATED_POSITION_LABELS:
        return [target]
    own_pos = current_user.designated_position_key()
    if own_pos:
        return [own_pos]
    return ['ceo']


def _extract_selected_positions(form):
    positions = [p.strip().lower() for p in form.getlist('positions') if p.strip().lower() in DESIGNATED_POSITION_LABELS]
    if not positions:
        legacy_type = (form.get('schedule_type') or '').strip().lower()
        if legacy_type in DESIGNATED_POSITION_LABELS:
            positions = [legacy_type]
    return positions


def _pick_redirect_view(selected_positions, fallback='ceo'):
    if 'ceo' in selected_positions:
        return 'ceo'
    for key, _ in DESIGNATED_POSITIONS:
        if key in selected_positions:
            return key
    return fallback


def _get_staff_users_for_form():
    """Return active users sorted by name for optional additional participant selection."""
    return (
        User.query.filter(User.is_active.is_(True))
        .order_by(User.name.asc())
        .all()
    )


@admin_bp.route('/admin/schedule/new', methods=['GET', 'POST'])
@schedule_manage_required
def new_schedule():
    current_user = User.query.get(session['user_id'])
    users = _get_staff_users_for_form()
    position_holders = get_position_holders_map()
    target = (request.args.get('target') or '').strip().lower()
    initial_positions = _resolve_initial_positions(current_user, target)

    if request.method == 'POST':
        event_date = parse_event_date(request.form['event_date'])
        time_value = build_time_range(request.form)
        activity = request.form['activity'].strip()
        description = request.form.get('description', '').strip()
        location = request.form['location'].strip()
        google_location = request.form.get('google_location', '').strip()
        responsible_person = request.form['responsible_person'].strip()
        meeting_type = request.form.get('meeting_type', 'Meeting').strip() or 'Meeting'
        priority = request.form.get('priority', 'Normal')
        status = request.form.get('status', 'Planned')
        remark = request.form.get('remark', '').strip()
        notes = request.form.get('notes', '').strip()
        reschedule = request.form.get('reschedule', 'NO')
        given_time = request.form.get('given_time', '').strip()

        selected_positions = _extract_selected_positions(request.form)
        attendant_ids = request.form.getlist('attendants')

        if not selected_positions and not attendant_ids:
            flash('Please select at least one designated position or participant.', 'danger')
            return render_template(
                'admin_schedule_form.html',
                entry=None,
                users=users,
                designated_positions=DESIGNATED_POSITIONS,
                position_holders=position_holders,
                selected_positions=set(initial_positions),
                selected_user_ids=set(),
                default_date=event_date.strftime('%Y-%m-%d'),
                target=target,
            )

        try:
            entry = ScheduleEntry(
                event_date=event_date,
                time=time_value,
                activity=activity,
                description=description or None,
                location=location,
                google_location=google_location or None,
                responsible_person=responsible_person,
                meeting_type=meeting_type,
                priority=priority,
                status=status,
                remark=remark or None,
                notes=notes or None,
                reschedule=reschedule,
                given_time=given_time or None,
                created_by_id=current_user.id,
                updated_by_id=current_user.id,
                user_id=None,
            )
            db.session.add(entry)
            sync_meeting_participants(
                entry,
                position_keys=selected_positions,
                user_ids=attendant_ids,
                actor_user=current_user,
                action='created',
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Could not save schedule due to duplicate participant constraint. Please try again.', 'danger')
            return redirect(url_for('admin.new_schedule', target=target))
        except Exception as exc:
            db.session.rollback()
            flash(f'Failed to create schedule entry: {exc}', 'danger')
            return redirect(url_for('admin.new_schedule', target=target))

        # Trigger CEO notifications only if CEO is a participant in this meeting
        if 'ceo' in entry.participant_position_keys:
            try:
                from flask import current_app
                from app.services.scheduler import notify_ceo_on_event_change, check_and_trigger_pending_daily_digest
                notify_ceo_on_event_change(entry, action="created")
                check_and_trigger_pending_daily_digest(current_app._get_current_object(), entry.event_date)
            except Exception as e:
                print(f"[Admin Route Error triggering notification]: {e}")

        flash('Meeting created and synchronized across all selected participant schedules.', 'success')
        redirect_view = _pick_redirect_view(selected_positions, fallback='mine')
        return redirect(url_for('dashboard.schedule', view_type=redirect_view, date=event_date.strftime('%Y-%m-%d')))

    default_date = request.args.get('date') or date.today().strftime('%Y-%m-%d')
    return render_template(
        'admin_schedule_form.html',
        entry=None,
        users=users,
        designated_positions=DESIGNATED_POSITIONS,
        position_holders=position_holders,
        selected_positions=set(initial_positions),
        selected_user_ids=set(),
        default_date=default_date,
        target=target,
    )


@admin_bp.route('/admin/schedule/<int:entry_id>/edit', methods=['GET', 'POST'])
@schedule_manage_required
def edit_schedule(entry_id):
    current_user = User.query.get(session['user_id'])
    entry = ScheduleEntry.query.get_or_404(entry_id)

    if not entry.can_be_modified_by(current_user):
        flash('You do not have permission to edit this meeting.', 'danger')
        return redirect(url_for('dashboard.schedule'))

    users = _get_staff_users_for_form()
    position_holders = get_position_holders_map()

    if request.method == 'POST':
        selected_positions = _extract_selected_positions(request.form)
        attendant_ids = request.form.getlist('attendants')

        if not selected_positions and not attendant_ids:
            flash('Please keep at least one designated position or participant selected.', 'danger')
            return redirect(url_for('admin.edit_schedule', entry_id=entry.id))

        try:
            entry.event_date = parse_event_date(request.form['event_date'])
            entry.time = build_time_range(request.form, fallback=entry.time)
            entry.activity = request.form['activity'].strip()
            entry.description = request.form.get('description', '').strip() or None
            entry.location = request.form['location'].strip()
            entry.google_location = request.form.get('google_location', '').strip() or None
            entry.responsible_person = request.form['responsible_person'].strip()
            entry.meeting_type = request.form.get('meeting_type', entry.meeting_type or 'Meeting').strip() or 'Meeting'
            entry.priority = request.form.get('priority', entry.priority)
            entry.status = request.form.get('status', entry.status)
            entry.remark = request.form.get('remark', '').strip() or None
            entry.notes = request.form.get('notes', '').strip() or None
            entry.reschedule = request.form.get('reschedule', 'NO')
            entry.given_time = request.form.get('given_time', '').strip() or None
            entry.updated_by_id = current_user.id

            sync_meeting_participants(
                entry,
                position_keys=selected_positions,
                user_ids=attendant_ids,
                actor_user=current_user,
                action='updated',
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Could not update meeting due to duplicate participant constraint.', 'danger')
            return redirect(url_for('admin.edit_schedule', entry_id=entry.id))
        except Exception as exc:
            db.session.rollback()
            flash(f'Failed to update schedule entry: {exc}', 'danger')
            return redirect(url_for('admin.edit_schedule', entry_id=entry.id))

        if 'ceo' in entry.participant_position_keys and entry.status != 'Cancelled':
            try:
                from flask import current_app
                from app.services.scheduler import notify_ceo_on_event_change, check_and_trigger_pending_daily_digest
                notify_ceo_on_event_change(entry, action="updated")
                check_and_trigger_pending_daily_digest(current_app._get_current_object(), entry.event_date)
            except Exception as e:
                print(f"[Admin Route Error triggering notification]: {e}")

        flash('Meeting updated and synchronized across all participant calendars.', 'success')
        redirect_view = _pick_redirect_view(selected_positions, fallback='mine')
        return redirect(url_for('dashboard.schedule', view_type=redirect_view, date=entry.event_date.strftime('%Y-%m-%d')))

    sh, sm, smer, eh, em, emer = split_time_for_form(entry.time)
    selected_positions = set(entry.participant_position_keys)
    if not selected_positions and entry.schedule_type in DESIGNATED_POSITION_LABELS:
        selected_positions = {entry.schedule_type}

    return render_template(
        'admin_schedule_form.html',
        entry=entry,
        users=users,
        designated_positions=DESIGNATED_POSITIONS,
        position_holders=position_holders,
        selected_positions=selected_positions,
        selected_user_ids=entry.participant_user_ids,
        target=entry.schedule_type or 'ceo',
        start_hour=sh,
        start_minute=sm,
        start_meridiem=smer,
        end_hour=eh,
        end_minute=em,
        end_meridiem=emer,
    )


@admin_bp.route('/admin/schedule/<int:entry_id>/delete', methods=['GET', 'POST'])
@schedule_manage_required
def delete_schedule(entry_id):
    current_user = User.query.get(session['user_id'])
    entry = ScheduleEntry.query.get_or_404(entry_id)

    if not entry.can_be_modified_by(current_user):
        flash('You do not have permission to delete this meeting.', 'danger')
        return redirect(url_for('dashboard.schedule'))

    redirect_view = _pick_redirect_view(list(entry.participant_position_keys), fallback='ceo')
    title_snapshot = entry.activity
    date_snapshot = entry.event_date

    try:
        db.session.add(
            ScheduleAuditLog(
                schedule_entry_id=None,
                entry_snapshot_title=title_snapshot,
                actor_id=current_user.id,
                action='deleted',
                details=f"Deleted meeting '{title_snapshot}' scheduled for {date_snapshot}",
            )
        )
        db.session.delete(entry)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Failed to delete meeting: {exc}', 'danger')
        return redirect(url_for('dashboard.schedule', view_type=redirect_view))

    flash('Meeting cancelled/deleted across all participant schedules.', 'success')
    return redirect(url_for('dashboard.schedule', view_type=redirect_view))


@admin_bp.route('/admin/users', methods=['GET'])
@admin_only
def manage_users():
    users = User.query.order_by(User.name.asc()).all()
    return render_template('manage_users.html', users=users)


@admin_bp.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_only
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    occupied_roles = get_occupied_unique_roles(exclude_user_id=user.id)

    if request.method == 'POST':
        name = request.form['name'].strip()
        department = request.form['department'].strip()
        designation = request.form['designation'].strip()
        email = request.form['email'].strip()
        phone_number = request.form.get('phone_number', '').strip()
        password = request.form.get('password', '').strip()
        raw_role = request.form['role'].strip()
        new_is_active = request.form.get('is_active') == '1'

        if session.get('user_id') == user.id:
            new_is_active = True

        canonical_role = _CANONICAL_ROLE_MAP.get(raw_role.lower())
        if not canonical_role:
            flash('Invalid role selected.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        # Check email uniqueness
        existing = User.query.filter(func.lower(User.email) == email.lower(), User.id != user.id).first()
        if existing:
            flash('Email is already registered by another account.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        if new_is_active and not is_role_available(canonical_role, exclude_user_id=user.id):
            flash(f'Cannot assign role "{canonical_role}" because another active account already holds it.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        old_role = user.role
        old_active = user.is_active

        try:
            user.name = name
            user.department = department
            user.designation = designation
            user.email = email
            user.phone_number = phone_number
            user.role = canonical_role
            user.is_active = new_is_active
            if password:
                user.password = password

            db.session.flush()
            if (old_active and not new_is_active) or (old_role != canonical_role):
                unlink_user_from_position_participants(user, old_role=old_role)
            if new_is_active:
                relink_position_participants_for_user(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(f'Role "{canonical_role}" or email "{email}" conflicts with an existing active account.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        flash('User updated successfully.', 'success')
        return redirect(url_for('admin.manage_users'))

    return render_template(
        'admin_edit_user.html',
        user=user,
        allowed_roles=ALLOWED_REGISTRATION_ROLES,
        occupied_roles=occupied_roles,
    )


@admin_bp.route('/admin/users/<int:user_id>/toggle-active', methods=['POST'])
@admin_only
def toggle_user_active(user_id):
    if session.get('user_id') == user_id:
        flash('You cannot deactivate your own admin account.', 'danger')
        return redirect(url_for('admin.manage_users'))

    user = User.query.get_or_404(user_id)
    target_active = not user.is_active

    if target_active and not is_role_available(user.role, exclude_user_id=user.id):
        flash(
            f'Cannot reactivate {user.name}: the "{user.role}" position is currently held by another active account. '
            f'Edit {user.name}\'s role first.',
            'danger',
        )
        return redirect(url_for('admin.manage_users'))

    try:
        user.is_active = target_active
        db.session.flush()
        if target_active:
            relink_position_participants_for_user(user)
        else:
            unlink_user_from_position_participants(user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Could not change account status due to role uniqueness conflict.', 'danger')
        return redirect(url_for('admin.manage_users'))

    state_label = 'activated' if target_active else 'deactivated'
    flash(f'User {user.name} has been {state_label}.', 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/admin/test-notifications', methods=['POST'])
@admin_only
def test_notifications():
    from app.services.notifier import send_sms, send_email
    from app.services.scheduler import send_daily_9am_whatsapp_digest
    from flask import current_app

    channel = request.form.get('channel', 'all')
    target_phone = request.form.get('phone_number', '').strip()
    target_email = request.form.get('email', '').strip()

    test_msg = "🔔 [TEST NOTIFICATION] CEO Sir Schedule Notification System is operating normally!"

    results = []
    if channel in ('sms', 'all'):
        ok = send_sms(target_phone, test_msg)
        results.append(f"SMS: {'Success' if ok else 'Failed/Logged'}")

    if channel in ('whatsapp', 'all'):
        send_daily_9am_whatsapp_digest(current_app._get_current_object())
        results.append("WhatsApp Daily Digest triggered.")

    if channel in ('email', 'all'):
        ok = send_email(target_email, "Test CEO Schedule Notification System", test_msg)
        results.append(f"Email: {'Success' if ok else 'Failed/Logged'}")

    flash(f"Notification Test Executed: {', '.join(results)}", 'info')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_only
def delete_user(user_id):
    if session.get('user_id') == user_id:
        flash('You cannot delete your own admin account.', 'danger')
        return redirect(url_for('admin.manage_users'))

    user = User.query.get_or_404(user_id)
    unlink_user_from_position_participants(user)
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.name} has been deleted.', 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/admin/schedule/<int:entry_id>/notify', methods=['GET', 'POST'])
@schedule_manage_required
def notify_attendants(entry_id):
    from app.models.notification import Notification
    entry = ScheduleEntry.query.get_or_404(entry_id)

    # Collect unique active participant User objects
    users_to_notify = {u.id: u for u in entry.attendants if u.is_active}
    for p in entry.participants:
        if p.user and p.user.is_active:
            users_to_notify[p.user.id] = p.user

    if not users_to_notify:
        flash('No active registered participants are assigned to this activity to notify.', 'warning')
        return redirect(url_for('dashboard.schedule'))

    sender_id = session.get('user_id')
    sender = User.query.get(sender_id)

    notified_count = 0
    for attendant in users_to_notify.values():
        existing = Notification.query.filter_by(
            user_id=attendant.id,
            schedule_entry_id=entry.id,
            acknowledged=False,
        ).first()
        if existing:
            continue

        notif = Notification(
            user_id=attendant.id,
            sender_id=sender.id,
            message=f"Activity: {entry.activity} at {entry.location}",
            time_needed=f"{entry.event_date.strftime('%A, %d - %B - %Y')} at {entry.time}",
            acknowledged=False,
            schedule_entry_id=entry.id,
        )
        db.session.add(notif)
        notified_count += 1

    if notified_count > 0:
        db.session.commit()
        flash(f'Notification sent to {notified_count} participant(s) successfully.', 'success')
    else:
        flash('All participants already have pending notifications for this activity.', 'info')

    target_v = _pick_redirect_view(list(entry.participant_position_keys), fallback='ceo')
    return redirect(url_for('dashboard.schedule', view_type=target_v, date=entry.event_date.strftime('%Y-%m-%d')))
