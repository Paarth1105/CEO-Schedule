from datetime import datetime
from app import db
from app.constants import STAFF_MANAGER_ROLES, role_to_position_key


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(120), nullable=False)
    designation = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(80), nullable=False, default='Employee')
    phone_number = db.Column(db.String(20), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_admin_role(self):
        return self.role in STAFF_MANAGER_ROLES

    def is_proprietor(self):
        return self.role == 'Proprietor'

    def designated_position_key(self):
        return role_to_position_key(self.role)

    def is_designated_role(self):
        return self.designated_position_key() is not None

    def can_create_meetings(self):
        return self.is_admin_role() or self.is_designated_role()

    def can_manage_proprietor_schedule(self):
        return self.role in {'Personal Assistant', 'Senior Assistant', 'Admin', 'Proprietor'}
