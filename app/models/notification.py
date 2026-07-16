from app import db
from datetime import datetime

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', foreign_keys=[user_id], backref='notifications')
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender = db.relationship('User', foreign_keys=[sender_id])
    message = db.Column(db.Text, nullable=False)
    time_needed = db.Column(db.String(80), nullable=False)
    acknowledged = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    schedule_entry_id = db.Column(db.Integer, db.ForeignKey('schedule_entry.id', ondelete='SET NULL'), nullable=True)
    schedule_entry = db.relationship('ScheduleEntry', backref='notifications')

