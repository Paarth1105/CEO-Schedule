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
    # Ensure new columns exist in request_message table (helps when schema changed without migrations)
    try:
        res = db.session.execute(text("PRAGMA table_info('request_message')")).fetchall()
        existing_cols = {row[1] for row in res}
        if 'feedback_time' not in existing_cols:
            db.session.execute(text("ALTER TABLE request_message ADD COLUMN feedback_time TEXT"))
        if 'feedback_message' not in existing_cols:
            db.session.execute(text("ALTER TABLE request_message ADD COLUMN feedback_message TEXT"))
        db.session.commit()
    except Exception:
        # For non-SQLite DBs, try generic ALTER TABLE if needed (ignore failures)
        try:
            if db.engine.dialect.has_table(db.engine.connect(), 'request_message'):
                db.session.execute(text("ALTER TABLE request_message ADD COLUMN feedback_time TEXT"))
                db.session.execute(text("ALTER TABLE request_message ADD COLUMN feedback_message TEXT"))
                db.session.commit()
        except Exception:
            db.session.rollback()

    try:
        res2 = db.session.execute(text("PRAGMA table_info('schedule_entry')")).fetchall()
        existing_cols2 = {row[1] for row in res2}
        if 'given_time' not in existing_cols2:
            db.session.execute(text("ALTER TABLE schedule_entry ADD COLUMN given_time TEXT"))
        if 'user_id' not in existing_cols2:
            db.session.execute(text("ALTER TABLE schedule_entry ADD COLUMN user_id INTEGER"))
        db.session.commit()
    except Exception:
        try:
            if db.engine.dialect.has_table(db.engine.connect(), 'schedule_entry'):
                db.session.execute(text("ALTER TABLE schedule_entry ADD COLUMN given_time TEXT"))
                db.session.execute(text("ALTER TABLE schedule_entry ADD COLUMN user_id INTEGER"))
                db.session.commit()
        except Exception:
            db.session.rollback()

    try:
        res3 = db.session.execute(text("PRAGMA table_info('notification')")).fetchall()
        existing_cols3 = {row[1] for row in res3}
        if 'schedule_entry_id' not in existing_cols3:
            db.session.execute(text("ALTER TABLE notification ADD COLUMN schedule_entry_id INTEGER"))
        db.session.commit()
    except Exception:
        try:
            if db.engine.dialect.has_table(db.engine.connect(), 'notification'):
                db.session.execute(text("ALTER TABLE notification ADD COLUMN schedule_entry_id INTEGER"))
                db.session.commit()
        except Exception:
            db.session.rollback()


from app.routes.auth import auth_bp
from app.routes.dashboard import dashboard_bp
from app.routes.admin import admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(admin_bp)

if __name__ == '__main__':
    app.run(debug=True)
