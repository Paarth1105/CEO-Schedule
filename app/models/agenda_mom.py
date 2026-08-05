from app import db
from datetime import datetime

class Agenda(db.Model):
    __tablename__ = 'agenda'
    
    id = db.Column(db.Integer, primary_key=True)
    schedule_entry_id = db.Column(db.Integer, db.ForeignKey('schedule_entry.id', ondelete='CASCADE'), unique=True, nullable=False)
    
    title = db.Column(db.String(200), nullable=True)
    event_date = db.Column(db.String(100), nullable=True)
    time = db.Column(db.String(100), nullable=True)
    location = db.Column(db.String(200), nullable=True)
    chairperson = db.Column(db.String(120), nullable=True)
    attendants = db.Column(db.Text, nullable=True)
    
    objective = db.Column(db.Text, nullable=True)
    schedule_table = db.Column(db.Text, nullable=True)  # JSON-serialized list of dicts
    follow_ups = db.Column(db.Text, nullable=True)
    tasks = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    schedule_entry = db.relationship('ScheduleEntry', backref=db.backref('agenda', uselist=False, cascade="all, delete-orphan"))


class MOM(db.Model):
    __tablename__ = 'mom'
    
    id = db.Column(db.Integer, primary_key=True)
    schedule_entry_id = db.Column(db.Integer, db.ForeignKey('schedule_entry.id', ondelete='CASCADE'), unique=True, nullable=False)
    
    meeting_date = db.Column(db.String(100), nullable=True)
    time = db.Column(db.String(100), nullable=True)
    location = db.Column(db.String(200), nullable=True)
    meeting_agenda = db.Column(db.Text, nullable=True)
    
    mom_table = db.Column(db.Text, nullable=True)  # JSON-serialized list of dicts: [ {sr_no, topic, points, actionable, responsibility} ]
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    schedule_entry = db.relationship('ScheduleEntry', backref=db.backref('mom', uselist=False, cascade="all, delete-orphan"))
