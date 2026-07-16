from app import db
from datetime import datetime

class RequestMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='requests')
    subject = db.Column(db.String(200), nullable=False)
    priority = db.Column(db.String(40), nullable=False)
    time_needed = db.Column(db.String(80), nullable=False)
    message = db.Column(db.Text, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    feedback_time = db.Column(db.String(80), nullable=True)
    feedback_message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), nullable=False, default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
