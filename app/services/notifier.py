import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Environment Configs
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+917887575304')

CEO_PHONE_NUMBER = os.environ.get('CEO_PHONE_NUMBER', '+919769568283')
CEO_EMAIL = os.environ.get('CEO_EMAIL', 'vikasabvp13@gmail.com')

SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')

def get_twilio_client():
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        return None
    try:
        from twilio.rest import Client
        return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    except Exception as e:
        print(f"[Notifier] Failed to initialize Twilio client: {e}")
        return None

def send_sms(to_phone: str, message_body: str) -> bool:
    """Send SMS via Twilio API (or log if credentials not configured)."""
    to_phone = to_phone or CEO_PHONE_NUMBER
    if not to_phone:
        print("[Notifier SMS] Target phone number is missing.")
        return False

    client = get_twilio_client()
    if client and TWILIO_PHONE_NUMBER:
        try:
            msg = client.messages.create(
                body=message_body,
                from_=TWILIO_PHONE_NUMBER,
                to=to_phone
            )
            print(f"[Notifier SMS] Sent successfully SID: {msg.sid}")
            return True
        except Exception as e:
            print(f"[Notifier SMS Error]: {e}")
            return False
    else:
        print(f"[Notifier SMS Simulated to {to_phone}]: {message_body}")
        return True

def send_whatsapp(to_phone: str, message_body: str, media_url: str = None, image_path: str = None) -> bool:
    """Send WhatsApp message via Twilio WhatsApp API (with optional media URL / image card)."""
    to_phone = to_phone or CEO_PHONE_NUMBER
    if not to_phone:
        print("[Notifier WhatsApp] Target phone number is missing.")
        return False

    # Format phone number for WhatsApp API
    if not to_phone.startswith('whatsapp:'):
        formatted_to = f"whatsapp:{to_phone}"
    else:
        formatted_to = to_phone

    formatted_from = TWILIO_WHATSAPP_NUMBER
    if not formatted_from.startswith('whatsapp:'):
        formatted_from = f"whatsapp:{formatted_from}"

    client = get_twilio_client()
    if client and TWILIO_ACCOUNT_SID:
        try:
            kwargs = {
                'body': message_body,
                'from_': formatted_from,
                'to': formatted_to
            }
            if media_url:
                kwargs['media_url'] = [media_url]

            msg = client.messages.create(**kwargs)
            print(f"[Notifier WhatsApp] Sent successfully SID: {msg.sid}")
            return True
        except Exception as e:
            print(f"[Notifier WhatsApp Error]: {e}")
            return False
    else:
        img_info = f" [Attached Image Card: {image_path}]" if image_path else ""
        print(f"[Notifier WhatsApp Simulated from {formatted_from} to {formatted_to}]{img_info}:\n{message_body}")
        return True

def send_email(to_email: str, subject: str, body_text: str, body_html: str = None) -> bool:
    """Send Email via SMTP (or log if SMTP parameters missing)."""
    to_email = to_email or CEO_EMAIL
    if not to_email:
        print("[Notifier Email] Target email is missing.")
        return False

    if SMTP_USER and SMTP_PASSWORD:
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = SMTP_USER
            msg['To'] = to_email

            msg.attach(MIMEText(body_text, 'plain'))
            if body_html:
                msg.attach(MIMEText(body_html, 'html'))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, to_email, msg.as_string())
            
            print(f"[Notifier Email] Sent email successfully to {to_email}")
            return True
        except Exception as e:
            print(f"[Notifier Email Error]: {e}")
            return False
    else:
        print(f"[Notifier Email Simulated to {to_email}] Subject: {subject}\n{body_text}")
        return True

def format_daily_schedule_whatsapp(schedule_entries, event_date_str: str) -> str:
    """Format full day schedule entries into clean WhatsApp markdown text."""
    if not schedule_entries:
        return f"📅 *Schedule Digest - {event_date_str}*\n\nGood Morning CEO Sir! ☀️\nNo events scheduled for today."

    lines = [
        f"📅 *CEO Sir Schedule - {event_date_str}*",
        f"Good Morning Sir! ☀️ Here is your schedule for today:\n"
    ]

    for idx, entry in enumerate(schedule_entries, 1):
        time_str = entry.time or "TBD"
        activity = entry.activity or "Scheduled Activity"
        location = entry.location or "N/A"
        resp_person = entry.responsible_person or "N/A"
        remark = f" ({entry.remark})" if entry.remark else ""
        map_link = f"\n   🔗 *Map:* {entry.google_location}" if entry.google_location else ""

        lines.append(
            f"{idx}️⃣ *{time_str}* - {activity}{remark}\n"
            f"   📍 *Location:* {location}\n"
            f"   👤 *Responsible:* {resp_person}{map_link}\n"
        )

    lines.append("Have a productive day ahead! 👍")
    return "\n".join(lines)
