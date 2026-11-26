import os
from datetime import date
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

basedir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.dirname(basedir)

app = Flask(__name__, instance_path=os.path.join(parent_dir, 'instance'))
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Automatically load .env if present
env_path = os.path.join(parent_dir, '.env')
if os.path.exists(env_path):
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key:
                        os.environ[key] = val
    except Exception as e:
        print("Error reading .env:", e)

# Production PostgreSQL database URL
DEFAULT_PG_URL = "postgresql://postgres:Software%402026@127.0.0.1:5432/ceo_schedule"
database_url = os.environ.get("DATABASE_URL")

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )
else:
    database_url = DEFAULT_PG_URL

print("DATABASE_URL =", repr(database_url))

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Disable pooling disconnect issues
if database_url and "postgresql" in database_url:
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

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
from app.models.schedule import ScheduleEntry, MeetingParticipant, ScheduleAuditLog
from app.models.agenda_mom import Agenda, MOM
from app.models.request import RequestMessage
from app.models.notification import Notification
from app.services.schedule_sync import ensure_schema_and_backfill


with app.app_context():
    ensure_schema_and_backfill()


@app.before_request
def enforce_active_session_user():
    from flask import session, redirect, url_for, flash, request
    if 'user_id' in session:
        if request.endpoint and request.endpoint.startswith('static'):
            return None
        user = User.query.get(session['user_id'])
        if not user or not user.is_active:
            session.clear()
            flash('Your account is inactive or unavailable. Please log in again.', 'warning')
            return redirect(url_for('auth.login'))
        session['user_role'] = user.role
        session['user_name'] = user.name


from app.routes.auth import auth_bp
from app.routes.dashboard import dashboard_bp
from app.routes.admin import admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(admin_bp)

# Start background notification scheduler (only once if debug reloader is enabled)
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    try:
        from app.services.scheduler import init_scheduler
        init_scheduler(app)
    except Exception as e:
        print("[Scheduler Error on Startup]:", e)

if __name__ == '__main__':
    app.run(debug=True)
