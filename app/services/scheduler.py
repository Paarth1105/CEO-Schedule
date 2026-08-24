import os
import re
from datetime import datetime, timedelta, date
from apscheduler.schedulers.background import BackgroundScheduler
from app.services.notifier import send_sms, send_whatsapp, send_email, format_daily_schedule_whatsapp
from app.services.image_generator import generate_schedule_image_card

scheduler = BackgroundScheduler(daemon=True)

# Memory tracker for daily schedule image digest dispatch
DAILY_DIGEST_SENT_DATE = None

def parse_time_str(time_str: str):
    """Safely parse various time formats like '09:30 AM', '9:30 AM', '14:30', '9:30'."""
    if not time_str:
        return None
    time_str = time_str.strip()
    
    formats = ["%I:%M %p", "%H:%M", "%I:%M%p", "%H:%M:%S"]
    for fmt in formats:
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            pass

    match = re.match(r'^(\d{1,2}):(\d{2})\s*([APap][Mm])?$', time_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        ampm = match.group(3)
        if ampm:
            ampm = ampm.upper()
            if ampm == 'PM' and hours < 12:
                hours += 12
            elif ampm == 'AM' and hours == 12:
                hours = 0
        try:
            return datetime.strptime(f"{hours:02d}:{minutes:02d}", "%H:%M").time()
        except ValueError:
            return None

    return None

def check_and_send_10min_alerts(app):
    """Background task running every minute to trigger 10-minute prior WhatsApp, SMS & Email alerts."""
    with app.app_context():
        from app import db
        from app.models.schedule import ScheduleEntry
        from app.models.user import User

        now_utc = datetime.utcnow()
        now_ist = now_utc + timedelta(hours=5, minutes=30)
        today = now_ist.date()

        entries = ScheduleEntry.query.filter_by(
            event_date=today,
            alert_sent_10m=False
        ).all()

        for entry in entries:
            parsed_time = parse_time_str(entry.time)
            if not parsed_time:
                continue

            event_dt = datetime.combine(today, parsed_time)
            time_diff_minutes = (event_dt - now_ist).total_seconds() / 60.0

            if 0 <= time_diff_minutes <= 11:
                message = (
                    f"⏰ *[UPCOMING MEETING REMINDER - 10 MIN PRIOR]*\n\n"
                    f"📌 *Activity:* {entry.activity}\n"
                    f"⏰ *Time:* {entry.time}\n"
                    f"📍 *Location:* {entry.location}\n"
                    f"👤 *Responsible:* {entry.responsible_person}"
                )
                if entry.remark:
                    message += f"\n📝 *Remark:* {entry.remark}"
                if entry.google_location:
                    message += f"\n🔗 *Location Map:* {entry.google_location}"

                print(f"[Scheduler] Triggering 10-min WhatsApp alert for Entry ID {entry.id}: {entry.activity}")
                
                ceo_user = User.query.filter(User.role.ilike('%CEO%')).first()
                target_phone = ceo_user.phone_number if (ceo_user and ceo_user.phone_number) else None
                target_email = ceo_user.email if (ceo_user and ceo_user.email) else None

                # Dispatch to WhatsApp (primary), SMS, and Email
                wa_sent = send_whatsapp(target_phone, message)
                sms_sent = send_sms(target_phone, message)
                email_sent = send_email(target_email, f"Reminder: {entry.activity} at {entry.time}", message)

                entry.alert_sent_10m = True
                db.session.commit()

def send_daily_9am_whatsapp_digest(app, force=False):
    """
    Background task to send daily schedule summary as an IMAGE CARD to CEO Sir on WhatsApp.
    If schedule is not ready at 9 AM, it waits until schedule entries are created, then sends automatically!
    """
    global DAILY_DIGEST_SENT_DATE
    with app.app_context():
        from app.models.schedule import ScheduleEntry
        from app.models.user import User

        now_utc = datetime.utcnow()
        now_ist = now_utc + timedelta(hours=5, minutes=30)
        today = now_ist.date()

        # Check if already sent for today unless forced
        if DAILY_DIGEST_SENT_DATE == today and not force:
            return True

        today_entries = ScheduleEntry.query.filter_by(event_date=today).order_by(ScheduleEntry.time.asc()).all()

        if not today_entries and not force:
            print(f"[Scheduler] 9 AM Check: Schedule for today ({today}) is NOT READY yet. Will send schedule image card automatically once created.")
            return False

        date_formatted = today.strftime("%d %b %Y")
        
        # 1. Generate Schedule Image Card
        static_dir = os.path.join(app.root_path, 'static', 'generated_digests')
        img_filename = f"schedule_{today.strftime('%Y-%m-%d')}.png"
        img_path = os.path.join(static_dir, img_filename)
        generate_schedule_image_card(today_entries, date_formatted, img_path)

        # 2. Format Text Caption
        digest_text = format_daily_schedule_whatsapp(today_entries, date_formatted)

        ceo_user = User.query.filter(User.role.ilike('%CEO%')).first()
        target_phone = ceo_user.phone_number if (ceo_user and ceo_user.phone_number) else None

        print(f"[Scheduler] Sending Daily Schedule IMAGE CARD via WhatsApp for {date_formatted}")
        send_whatsapp(target_phone, digest_text, image_path=img_path)
        DAILY_DIGEST_SENT_DATE = today
        return True

def check_and_trigger_pending_daily_digest(app, event_date):
    """Checks if daily schedule image digest was pending for today, and sends it if ready."""
    global DAILY_DIGEST_SENT_DATE
    now_utc = datetime.utcnow()
    now_ist = now_utc + timedelta(hours=5, minutes=30)
    today = now_ist.date()

    if event_date == today and DAILY_DIGEST_SENT_DATE != today:
        print(f"[Scheduler] Schedule created/updated for today ({today}). Auto-triggering pending schedule image digest to CEO Sir!")
        send_daily_9am_whatsapp_digest(app, force=True)

def notify_ceo_on_event_change(entry, action="created"):
    """Instantly send a WhatsApp alert to CEO Sir whenever an event is created or modified."""
    from app.models.user import User

    ceo_user = User.query.filter(User.role.ilike('%CEO%')).first()
    target_phone = ceo_user.phone_number if (ceo_user and ceo_user.phone_number) else None

    action_label = "NEW EVENT SCHEDULED" if action == "created" else "EVENT UPDATED"
    date_str = entry.event_date.strftime("%d %b %Y") if entry.event_date else "Today"

    message = (
        f"📢 *[{action_label} FOR CEO SIR]*\n\n"
        f"📌 *Activity:* {entry.activity}\n"
        f"📅 *Date:* {date_str}\n"
        f"⏰ *Time:* {entry.time}\n"
        f"📍 *Location:* {entry.location}\n"
        f"👤 *Responsible:* {entry.responsible_person}\n"
        f"📊 *Status:* {entry.status}"
    )
    if entry.remark:
        message += f"\n📝 *Remark:* {entry.remark}"
    if entry.google_location:
        message += f"\n🔗 *Location Map:* {entry.google_location}"

    print(f"[Scheduler] Sending instant WhatsApp event notification ({action}): {entry.activity}")
    send_whatsapp(target_phone, message)

def init_scheduler(app):
    """Initialize APScheduler with background jobs."""
    if not scheduler.running:
        # Job 1: Check for 10-minute upcoming events every minute
        scheduler.add_job(
            id='check_10min_alerts',
            func=check_and_send_10min_alerts,
            args=[app],
            trigger='interval',
            seconds=60,
            replace_existing=True
        )

        # Job 2: Send daily schedule summary at 9:00 AM IST
        scheduler.add_job(
            id='daily_9am_whatsapp',
            func=send_daily_9am_whatsapp_digest,
            args=[app],
            trigger='cron',
            hour=9,
            minute=0,
            replace_existing=True
        )

        try:
            scheduler.start()
            print("[Scheduler] APScheduler started successfully.")
        except Exception as e:
            print(f"[Scheduler Error]: {e}")
