from app import db
from datetime import datetime

schedule_attendants = db.Table('schedule_attendants',
    db.Column('schedule_entry_id', db.Integer, db.ForeignKey('schedule_entry.id', ondelete='CASCADE'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)
)

class ScheduleEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(20), nullable=False)
    activity = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(120), nullable=False)
    google_location = db.Column(db.String(500), nullable=True)
    responsible_person = db.Column(db.String(120), nullable=False)
    priority = db.Column(db.String(40), nullable=False, default='Normal')
    status = db.Column(db.String(40), nullable=False, default='Planned')
    remark = db.Column(db.String(200), nullable=True)
    reschedule = db.Column(db.String(10), nullable=False, default='NO')
    given_time = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user = db.relationship('User', backref='schedules')
    attendants = db.relationship('User', secondary=schedule_attendants, backref=db.backref('attending_schedules', lazy='dynamic'))

