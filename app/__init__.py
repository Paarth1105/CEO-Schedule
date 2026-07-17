import os
from datetime import date
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

basedir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.dirname(basedir)

app = Flask(__name__, instance_path=os.path.join(parent_dir, 'instance'))
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
# Allow configuring a Postgres (or any SQLALCHEMY) database via environment variable
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'sqlite:///' + os.path.join(parent_dir, 'instance', 'schedule_app.db')
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

import os

database_url = os.getenv("DATABASE_URL")
print("DATABASE_URL =", repr(database_url))

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )
else:
    database_url = "sqlite:///" + os.path.join(
        parent_dir,
        "instance",
        "schedule_app.db"
    )

print("Using database:", database_url)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url

db = SQLAlchemy(app)

@app.context_processor
def inject_common_context():
    from flask import session
    from app.models.notification import Notification
    from datetime import timedelta
    today = date.today()
    unread_notifications = []
    if 'user_id' in session:
        try:
            unread_notifications = Notification.query.filter_by(
                user_id=session['user_id'],
                acknowledged=False
            ).order_by(Notification.created_at.desc()).all()
        except Exception:
            # Safe fallback if table doesn't exist yet
            pass

    def to_ist(utc_dt):
        if not utc_dt:
            return None
        return utc_dt + timedelta(hours=5, minutes=30)

    return {
        'today_label': today.strftime('%d %b %Y'),
        'today': today,
        'unread_notifications': unread_notifications,
        'to_ist': to_ist,
    }

from app.models.user import User
from app.models.schedule import ScheduleEntry
from app.models.request import RequestMessage
from app.models.notification import Notification

with app.app_context():
    db.create_all()
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)

        # Check request_message table
        if inspector.has_table('request_message'):
            columns = [c['name'] for c in inspector.get_columns('request_message')]
            modified = False
            if 'feedback_time' not in columns:
                db.session.execute(text("ALTER TABLE request_message ADD COLUMN feedback_time TEXT"))
                modified = True
            if 'feedback_message' not in columns:
                db.session.execute(text("ALTER TABLE request_message ADD COLUMN feedback_message TEXT"))
                modified = True
            if modified:
                db.session.commit()

        # Check schedule_entry table
        if inspector.has_table('schedule_entry'):
            columns2 = [c['name'] for c in inspector.get_columns('schedule_entry')]
            modified2 = False
            if 'given_time' not in columns2:
                db.session.execute(text("ALTER TABLE schedule_entry ADD COLUMN given_time TEXT"))
                modified2 = True
            if 'user_id' not in columns2:
                db.session.execute(text("ALTER TABLE schedule_entry ADD COLUMN user_id INTEGER"))
                modified2 = True
            if modified2:
                db.session.commit()

        # Check notification table
        if inspector.has_table('notification'):
            columns3 = [c['name'] for c in inspector.get_columns('notification')]
            if 'schedule_entry_id' not in columns3:
                db.session.execute(text("ALTER TABLE notification ADD COLUMN schedule_entry_id INTEGER"))
                db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("Schema verification warning:", e)


from app.routes.auth import auth_bp
from app.routes.dashboard import dashboard_bp
from app.routes.admin import admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(admin_bp)

if __name__ == '__main__':
    app.run(debug=True)
