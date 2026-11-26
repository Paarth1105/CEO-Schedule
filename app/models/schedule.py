from datetime import datetime
from app import db
from app.constants import DESIGNATED_POSITION_KEYS, DESIGNATED_POSITION_LABELS


schedule_attendants = db.Table(
    'schedule_attendants',
    db.Column('schedule_entry_id', db.Integer, db.ForeignKey('schedule_entry.id', ondelete='CASCADE'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
)


class MeetingParticipant(db.Model):
    __tablename__ = 'meeting_participant'

    id = db.Column(db.Integer, primary_key=True)
    schedule_entry_id = db.Column(
        db.Integer,
        db.ForeignKey('schedule_entry.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )
    position_key = db.Column(db.String(40), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    schedule_entry = db.relationship('ScheduleEntry', back_populates='participants')
    user = db.relationship('User', foreign_keys=[user_id])


class ScheduleAuditLog(db.Model):
    __tablename__ = 'schedule_audit_log'

    id = db.Column(db.Integer, primary_key=True)
    schedule_entry_id = db.Column(
        db.Integer,
        db.ForeignKey('schedule_entry.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    entry_snapshot_title = db.Column(db.String(200), nullable=True)
    actor_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    action = db.Column(db.String(40), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    schedule_entry = db.relationship('ScheduleEntry', back_populates='audit_logs')
    actor = db.relationship('User', foreign_keys=[actor_id])


class ScheduleEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_date = db.Column(db.Date, nullable=False, index=True)
    time = db.Column(db.String(20), nullable=False)
    activity = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(120), nullable=False)
    google_location = db.Column(db.String(500), nullable=True)
    responsible_person = db.Column(db.String(120), nullable=False)
    meeting_type = db.Column(db.String(60), nullable=True, default='Meeting')
    priority = db.Column(db.String(40), nullable=False, default='Normal')
    status = db.Column(db.String(40), nullable=False, default='Planned')
    remark = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    reschedule = db.Column(db.String(10), nullable=False, default='NO')
    given_time = db.Column(db.String(120), nullable=True)
    alert_sent_10m = db.Column(db.Boolean, default=False, nullable=False)
    schedule_type = db.Column(db.String(40), default='ceo', nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], backref='schedules')
    creator = db.relationship('User', foreign_keys=[created_by_id])
    updater = db.relationship('User', foreign_keys=[updated_by_id])
    attendants = db.relationship(
        'User',
        secondary=schedule_attendants,
        backref=db.backref('attending_schedules', lazy='dynamic'),
    )
    participants = db.relationship(
        'MeetingParticipant',
        back_populates='schedule_entry',
        cascade='all, delete-orphan',
        lazy='selectin',
    )
    audit_logs = db.relationship(
        'ScheduleAuditLog',
        back_populates='schedule_entry',
        cascade='save-update, merge',
        order_by='ScheduleAuditLog.created_at.desc()',
    )

    @property
    def participant_position_keys(self):
        return {p.position_key for p in self.participants if p.position_key}

    @property
    def participant_user_ids(self):
        return {p.user_id for p in self.participants if p.user_id is not None}

    @property
    def is_combined_meeting(self):
        return set(DESIGNATED_POSITION_KEYS).issubset(self.participant_position_keys)

    def display_participants(self):
        """Return deduplicated, ordered participant display dicts for templates and exports."""
        items = []
        seen_user_ids = set()
        by_pos = {}
        extra_users = []

        for p in self.participants:
            if p.position_key:
                by_pos[p.position_key] = p
                if p.user_id:
                    seen_user_ids.add(p.user_id)
            elif p.user_id and p.user:
                extra_users.append(p.user)

        for key in DESIGNATED_POSITION_KEYS:
            if key in by_pos:
                p = by_pos[key]
                pos_label = DESIGNATED_POSITION_LABELS[key]
                holder_name = p.user.name if p.user else None
                items.append({
                    'label': pos_label,
                    'sublabel': holder_name,
                    'display': f"{pos_label} ({holder_name})" if holder_name else pos_label,
                    'is_position': True,
                    'position_key': key,
                    'user_id': p.user_id,
                })

        for u in sorted(extra_users, key=lambda x: (x.name or '').lower()):
            if u.id not in seen_user_ids:
                seen_user_ids.add(u.id)
                items.append({
                    'label': u.name,
                    'sublabel': u.role,
                    'display': u.name,
                    'is_position': False,
                    'position_key': None,
                    'user_id': u.id,
                })

        # Fallback for any legacy attendants not yet represented in MeetingParticipant
        for u in sorted(self.attendants, key=lambda x: (x.name or '').lower()):
            if u.id not in seen_user_ids:
                seen_user_ids.add(u.id)
                items.append({
                    'label': u.name,
                    'sublabel': u.role,
                    'display': u.name,
                    'is_position': False,
                    'position_key': None,
                    'user_id': u.id,
                })
        return items

    def can_be_modified_by(self, user):
        """Check whether the given user is authorized to edit or delete this schedule entry."""
        if not user or not getattr(user, 'is_active', True):
            return False
        if user.is_admin_role():
            return True
        if self.created_by_id == user.id or self.user_id == user.id:
            return True
        if user.role == 'Proprietor' and (
            self.schedule_type == 'proprietor' or self.participant_position_keys == {'proprietor'}
        ):
            return True
        return False
