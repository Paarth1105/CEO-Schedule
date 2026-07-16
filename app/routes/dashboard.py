from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import or_
from app import db
from app.models.schedule import ScheduleEntry
from app.models.request import RequestMessage
from app.models.user import User
from app.models.notification import Notification

dashboard_bp = Blueprint('dashboard', __name__)


def login_required(view):
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


@dashboard_bp.route('/dashboard')
@login_required
def schedule():
    today = date.today()
    selected_date = request.args.get('date')
    range_filter = request.args.get('range', 'today')
    rescheduled_only = request.args.get('rescheduled') == '1'
    current_user = User.query.get(session['user_id'])
    
    view_type = request.args.get('view_type', 'ceo')
    employee_id = request.args.get('employee_id', type=int)
    target_employee = None

    focus_date = None
    if selected_date:
        try:
            focus_date = date.fromisoformat(selected_date)
        except ValueError:
            focus_date = None

    if focus_date:
        range_filter = 'day'
        range_label = f"Schedule for {focus_date.strftime('%d %b %Y')}"
        query = ScheduleEntry.query.filter(ScheduleEntry.event_date == focus_date)
    else:
        if range_filter == '7d':
            start_date = today - timedelta(days=7)
            range_label = 'Last 7 days'
        elif range_filter == '15d':
            start_date = today - timedelta(days=15)
            range_label = 'Last 15 days'
        elif range_filter == '1m':
            start_date = today - timedelta(days=30)
            range_label = 'Last month'
        elif range_filter == 'upcoming':
            start_date = today + timedelta(days=1)
            range_label = 'Upcoming'
        else:
            range_filter = 'today'
            start_date = today
            range_label = "Today's schedule"

        query = ScheduleEntry.query
        if range_filter == 'upcoming':
            query = query.filter(ScheduleEntry.event_date >= start_date)
        else:
            query = query.filter(ScheduleEntry.event_date >= start_date, ScheduleEntry.event_date <= today)

    # Filter based on view_type and user role
    if view_type == 'mine':
        query = query.filter(ScheduleEntry.user_id == current_user.id)
    elif view_type == 'employee' and current_user.is_admin_role():
        if employee_id:
            target_employee = User.query.get(employee_id)
            query = query.filter(ScheduleEntry.user_id == employee_id)
        else:
            query = query.filter(ScheduleEntry.user_id == -1) # empty
    else:
        view_type = 'ceo'
        query = query.filter(ScheduleEntry.user_id.is_(None))

    if rescheduled_only:
        query = query.filter(ScheduleEntry.reschedule == 'YES')
        range_label = f"{range_label} - Rescheduled"

    entries = query.order_by(ScheduleEntry.event_date.asc()).all()
    
    def get_start_time_sort_key(entry):
        time_str = entry.time or ''
        start_part = time_str.split('-')[0].strip() if '-' in time_str else time_str.strip()
        if not start_part:
            return (2, 0, 0)
        try:
            parsed = datetime.strptime(start_part, "%I:%M %p")
            return (0, parsed.hour, parsed.minute)
        except ValueError:
            try:
                parsed = datetime.strptime(start_part, "%H:%M")
                return (0, parsed.hour, parsed.minute)
            except ValueError:
                return (1, start_part, 0)

    entries.sort(key=lambda x: (x.event_date, get_start_time_sort_key(x), x.id))
    users = User.query.order_by(User.name.asc()).all()
    return render_template(
        'dashboard.html',
        entries=entries,
        today=today,
        current_user=current_user,
        range_filter=range_filter,
        range_label=range_label,
        rescheduled=rescheduled_only,
        view_type=view_type,
        target_employee=target_employee,
        users=users,
    )


@dashboard_bp.route('/generate-request', methods=['GET', 'POST'])
@login_required
def generate_request():
    if request.method == 'POST':
        subject = request.form['subject']
        priority = request.form['priority']
        discussion_date = request.form.get('discussion_date', '').strip()
        discussion_hour = request.form.get('discussion_hour', '').strip()
        discussion_minute = request.form.get('discussion_minute', '').strip()
        discussion_meridiem = request.form.get('discussion_meridiem', '').strip()
        time_needed = f"{discussion_date} {discussion_hour}:{discussion_minute} {discussion_meridiem}" if discussion_date else ''
        message = request.form.get('message', '')
        req = RequestMessage(user_id=session['user_id'], subject=subject, priority=priority, time_needed=time_needed, message=message)
        db.session.add(req)
        db.session.commit()
        flash('Request sent successfully.', 'success')
        return redirect(url_for('dashboard.request_history'))
    return render_template('generate_request.html')


@dashboard_bp.route('/request/<int:req_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_request(req_id):
    current_user = User.query.get(session['user_id'])
    req = RequestMessage.query.get_or_404(req_id)
    # Only the owner (employee) or admin (PA/SA) may edit; employees cannot edit after feedback exists
    if request.method == 'POST':
        if not (current_user.id == req.user_id or current_user.is_admin_role()):
            flash('Not authorized to edit this request.', 'danger')
            return redirect(url_for('dashboard.request_history'))
        if req.feedback:
            flash('Cannot edit a request that already has feedback.', 'warning')
            return redirect(url_for('dashboard.request_history'))

        req.subject = request.form['subject']
        req.priority = request.form['priority']
        discussion_date = request.form.get('discussion_date', '').strip()
        discussion_hour = request.form.get('discussion_hour', '').strip()
        discussion_minute = request.form.get('discussion_minute', '').strip()
        discussion_meridiem = request.form.get('discussion_meridiem', '').strip()
        req.time_needed = f"{discussion_date} {discussion_hour}:{discussion_minute} {discussion_meridiem}" if discussion_date else ''
        req.message = request.form.get('message', '')
        db.session.commit()
        flash('Request updated.', 'success')
        return redirect(url_for('dashboard.request_history'))

    discussion_date = ''
    discussion_hour = ''
    discussion_minute = ''
    discussion_meridiem = ''
    if req.time_needed:
        parts = req.time_needed.split(' ')
        if len(parts) >= 3:
            discussion_date = parts[0]
            time_part = parts[1]
            discussion_meridiem = parts[2]
            time_values = time_part.split(':')
            discussion_hour = time_values[0]
            discussion_minute = time_values[1]
    return render_template('edit_request.html', req=req, current_user=current_user, discussion_date=discussion_date, discussion_hour=discussion_hour, discussion_minute=discussion_minute, discussion_meridiem=discussion_meridiem)



@dashboard_bp.route('/request/<int:req_id>/reply', methods=['GET', 'POST'])
@login_required
def reply_request(req_id):
    current_user = User.query.get(session['user_id'])
    if not current_user.is_admin_role():
        flash('Only PA/SA can send replies.', 'danger')
        return redirect(url_for('dashboard.request_history'))

    req = RequestMessage.query.get_or_404(req_id)
    if request.method == 'POST':
        reply_date = request.form.get('reply_date', '').strip()
        reply_hour = request.form.get('reply_hour', '').strip()
        reply_minute = request.form.get('reply_minute', '').strip()
        reply_meridiem = request.form.get('reply_meridiem', '').strip()
        time_given = f"{reply_date} {reply_hour}:{reply_minute} {reply_meridiem}" if reply_date else ''
        message = request.form.get('message', '').strip()
        req.feedback_time = time_given
        req.feedback_message = message
        req.status = 'Replied'
        db.session.commit()
        flash('Reply sent to employee.', 'success')
        return redirect(url_for('dashboard.request_history'))

    return render_template('reply_request.html', req=req, current_user=current_user)


@dashboard_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    current_user = User.query.get(session['user_id'])
    if request.method == 'POST':
        name = request.form['name'].strip()
        department = request.form['department'].strip()
        designation = request.form['designation'].strip()
        email = request.form['email'].strip()
        password = request.form.get('password', '').strip()

        # Check if email is already taken by another user
        existing_user = User.query.filter(User.email == email, User.id != current_user.id).first()
        if existing_user:
            flash('This email is already in use by another account.', 'danger')
            return redirect(url_for('dashboard.profile'))

        current_user.name = name
        current_user.department = department
        current_user.designation = designation
        current_user.email = email
        if password:
            current_user.password = password
            
        db.session.commit()
        session['user_name'] = current_user.name
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('dashboard.profile'))

    return render_template('profile.html', current_user=current_user)


@dashboard_bp.route('/request-history')
@login_required
def request_history():
    current_user = User.query.get(session['user_id'])
    if current_user.is_admin_role():
        requests = RequestMessage.query.order_by(RequestMessage.created_at.desc()).all()
    else:
        requests = RequestMessage.query.filter_by(user_id=session['user_id']).order_by(RequestMessage.created_at.desc()).all()
    return render_template('request_history.html', requests=requests, current_user=current_user)


@dashboard_bp.route('/feedback-history', methods=['GET', 'POST'])
@login_required
def feedback_history():
    current_user = User.query.get(session['user_id'])
    if request.method == 'POST':
        request_id = request.form.get('request_id')
        req = RequestMessage.query.get(request_id)
        if not req:
            flash('Request not found.', 'danger')
            return redirect(url_for('dashboard.feedback_history'))

        if current_user.is_admin_role():
            feedback = request.form['feedback']
            status = request.form['status']
            req.feedback = feedback
            req.status = status
            db.session.commit()
            flash('Feedback updated.', 'success')
        elif request.form.get('action') == 'acknowledge':
            req.status = 'Acknowledged'
            db.session.commit()
            flash('Acknowledged successfully.', 'success')

    feedback_query = RequestMessage.query.filter(
        or_(
            RequestMessage.feedback.isnot(None),
            RequestMessage.feedback != '',
            RequestMessage.feedback_message.isnot(None),
            RequestMessage.feedback_message != '',
            RequestMessage.feedback_time.isnot(None),
            RequestMessage.feedback_time != ''
        )
    )

    if current_user.is_admin_role():
        requests = feedback_query.order_by(RequestMessage.created_at.desc()).all()
    else:
        requests = feedback_query.filter(RequestMessage.user_id == current_user.id).order_by(RequestMessage.created_at.desc()).all()
    return render_template('feedback_history.html', requests=requests, current_user=current_user)


@dashboard_bp.route('/calendar')
@login_required
def calendar_view():
    current_user = User.query.get(session['user_id'])
    if current_user.is_admin_role():
        # SA/PA can see CEO schedule on the calendar
        entries = ScheduleEntry.query.filter(ScheduleEntry.user_id.is_(None)).order_by(ScheduleEntry.event_date.asc()).all()
    else:
        # Employees see CEO schedule and their own personal schedule
        entries = ScheduleEntry.query.filter(
            or_(
                ScheduleEntry.user_id.is_(None),
                ScheduleEntry.user_id == current_user.id
            )
        ).order_by(ScheduleEntry.event_date.asc()).all()

    events = [
        {
            'date': entry.event_date.strftime('%Y-%m-%d'),
            'activity': entry.activity,
            'priority': entry.priority
        }
        for entry in entries
    ]
    return render_template('calendar.html', events=events)


@dashboard_bp.route('/employees')
@login_required
def employees_list():
    current_user = User.query.get(session['user_id'])
    if not current_user.is_admin_role():
        flash('Only Personal Assistant or Senior Assistant can view employees.', 'danger')
        return redirect(url_for('dashboard.schedule'))
    employees = User.query.filter_by(role='Employee').order_by(User.name.asc()).all()
    return render_template('employees.html', employees=employees, current_user=current_user)


@dashboard_bp.route('/schedule/new', methods=['GET', 'POST'])
@login_required
def new_employee_schedule():
    current_user = User.query.get(session['user_id'])
    if request.method == 'POST':
        event_date_str = request.form['event_date']
        try:
            event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
        except ValueError:
            event_date = date.fromisoformat(event_date_str)

        start_time = request.form.get('start_hour', '').strip()
        start_minute = request.form.get('start_minute', '').strip()
        start_meridiem = request.form.get('start_meridiem', '').strip()
        end_time = request.form.get('end_hour', '').strip()
        end_minute = request.form.get('end_minute', '').strip()
        end_meridiem = request.form.get('end_meridiem', '').strip()

        start_value = f"{start_time}:{start_minute} {start_meridiem}" if start_time and start_minute else ''
        end_value = f"{end_time}:{end_minute} {end_meridiem}" if end_time and end_minute else ''
        time_value = f"{start_value} - {end_value}" if start_value and end_value else (start_value or end_value or '')

        activity = request.form.get('activity', 'Personal Duty')
        location = request.form.get('location', 'Office')
        priority = request.form.get('priority', 'Normal')
        status = request.form.get('status', 'Planned')
        remark = request.form.get('remark', '')
        reschedule = request.form.get('reschedule', 'NO')
        given_time = request.form.get('given_time', '').strip()

        entry = ScheduleEntry(
            event_date=event_date,
            time=time_value,
            activity=activity,
            location=location,
            responsible_person=current_user.name,
            priority=priority,
            status=status,
            remark=remark,
            reschedule=reschedule,
            given_time=given_time,
            user_id=current_user.id
        )
        db.session.add(entry)
        db.session.commit()
        flash('Schedule entry created successfully.', 'success')
        return redirect(url_for('dashboard.schedule', view_type='mine'))

    return render_template('employee_schedule_form.html', entry=None)


@dashboard_bp.route('/schedule/<int:entry_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_employee_schedule(entry_id):
    current_user = User.query.get(session['user_id'])
    entry = ScheduleEntry.query.get_or_404(entry_id)

    # Must be owner of the schedule or SA/PA
    if not (entry.user_id == current_user.id or current_user.is_admin_role()):
        flash('Not authorized to edit this schedule entry.', 'danger')
        return redirect(url_for('dashboard.schedule'))

    if request.method == 'POST':
        event_date_str = request.form['event_date']
        try:
            entry.event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
        except ValueError:
            entry.event_date = date.fromisoformat(event_date_str)

        start_time = request.form.get('start_hour', '').strip()
        start_minute = request.form.get('start_minute', '').strip()
        start_meridiem = request.form.get('start_meridiem', '').strip()
        end_time = request.form.get('end_hour', '').strip()
        end_minute = request.form.get('end_minute', '').strip()
        end_meridiem = request.form.get('end_meridiem', '').strip()

        start_value = f"{start_time}:{start_minute} {start_meridiem}" if start_time and start_minute else ''
        end_value = f"{end_time}:{end_minute} {end_meridiem}" if end_time and end_minute else ''
        entry.time = f"{start_value} - {end_value}" if start_value and end_value else (start_value or end_value or entry.time)

        entry.activity = request.form.get('activity', entry.activity)
        entry.location = request.form.get('location', entry.location)
        entry.priority = request.form.get('priority', entry.priority)
        entry.status = request.form.get('status', entry.status)
        entry.remark = request.form.get('remark', entry.remark)
        entry.reschedule = request.form.get('reschedule', entry.reschedule)
        entry.given_time = request.form.get('given_time', '').strip()

        db.session.commit()
        flash('Schedule entry updated.', 'success')

        if entry.user_id == current_user.id:
            return redirect(url_for('dashboard.schedule', view_type='mine'))
        else:
            return redirect(url_for('dashboard.schedule', view_type='employee', employee_id=entry.user_id))

    # Parse times for editing
    start_time, end_time = '', ''
    if entry.time:
        parts = [part.strip() for part in entry.time.split('-')]
        if len(parts) >= 2:
            start_time, end_time = parts[0], parts[1]
        else:
            start_time = parts[0]

    start_hour, start_minute, start_meridiem = '', '', ''
    if start_time and ':' in start_time:
        try:
            time_part, meridiem_part = start_time.split()
            h, m = time_part.split(':')
            start_hour = h
            start_minute = m
            start_meridiem = meridiem_part
        except Exception:
            pass

    end_hour, end_minute, end_meridiem = '', '', ''
    if end_time and ':' in end_time:
        try:
            time_part, meridiem_part = end_time.split()
            h, m = time_part.split(':')
            end_hour = h
            end_minute = m
            end_meridiem = meridiem_part
        except Exception:
            pass

    return render_template(
        'employee_schedule_form.html',
        entry=entry,
        start_hour=start_hour,
        start_minute=start_minute,
        start_meridiem=start_meridiem,
        end_hour=end_hour,
        end_minute=end_minute,
        end_meridiem=end_meridiem
    )


@dashboard_bp.route('/schedule/<int:entry_id>/delete')
@login_required
def delete_employee_schedule(entry_id):
    current_user = User.query.get(session['user_id'])
    entry = ScheduleEntry.query.get_or_404(entry_id)

    # Must be owner of the schedule or SA/PA
    if not (entry.user_id == current_user.id or current_user.is_admin_role()):
        flash('Not authorized to delete this schedule entry.', 'danger')
        return redirect(url_for('dashboard.schedule'))

    db.session.delete(entry)
    db.session.commit()
    flash('Schedule entry deleted.', 'success')

    if entry.user_id == current_user.id:
        return redirect(url_for('dashboard.schedule', view_type='mine'))
    else:
        return redirect(url_for('dashboard.schedule', view_type='employee', employee_id=entry.user_id))


@dashboard_bp.route('/employees/<int:employee_id>/notify', methods=['GET', 'POST'])
@login_required
def notify_employee(employee_id):
    current_user = User.query.get(session['user_id'])
    if not current_user.is_admin_role():
        flash('Only Personal Assistant or Senior Assistant can notify employees.', 'danger')
        return redirect(url_for('dashboard.schedule'))

    employee = User.query.get_or_404(employee_id)
    if employee.role != 'Employee':
        flash('Can only notify employees.', 'warning')
        return redirect(url_for('dashboard.employees_list'))

    # Fetch CEO schedule entries to allow linking an invitation
    ceo_schedules = ScheduleEntry.query.filter(ScheduleEntry.user_id.is_(None)).order_by(ScheduleEntry.event_date.desc(), ScheduleEntry.id.desc()).all()

    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        notification_date = request.form.get('notification_date', '').strip()
        notification_hour = request.form.get('notification_hour', '').strip()
        notification_minute = request.form.get('notification_minute', '').strip()
        notification_meridiem = request.form.get('notification_meridiem', '').strip()
        schedule_entry_id = request.form.get('schedule_entry_id', '').strip()

        time_value = f"{notification_date} {notification_hour}:{notification_minute} {notification_meridiem}" if notification_date else ''

        if not message or not time_value:
            flash('All fields are required.', 'danger')
            return redirect(url_for('dashboard.notify_employee', employee_id=employee_id))

        notif = Notification(
            user_id=employee.id,
            sender_id=current_user.id,
            message=message,
            time_needed=time_value,
            acknowledged=False
        )
        if schedule_entry_id:
            notif.schedule_entry_id = int(schedule_entry_id)

        db.session.add(notif)
        db.session.commit()
        flash(f'Notification sent to {employee.name} successfully.', 'success')
        return redirect(url_for('dashboard.employees_list'))

    return render_template('notify_employee.html', employee=employee, ceo_schedules=ceo_schedules)


@dashboard_bp.route('/notification/<int:notif_id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_notification(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != session['user_id']:
        flash('Not authorized to acknowledge this notification.', 'danger')
        return redirect(url_for('dashboard.schedule'))

    notif.acknowledged = True

    # Automatically add to attendants list if this notification is associated with a schedule entry (meeting)
    if notif.schedule_entry_id:
        entry = ScheduleEntry.query.get(notif.schedule_entry_id)
        if entry:
            user = User.query.get(notif.user_id)
            if user and user not in entry.attendants:
                entry.attendants.append(user)

    db.session.commit()
    flash('Notification acknowledged.', 'success')
    return redirect(url_for('dashboard.notifications'))


@dashboard_bp.route('/notifications')
@login_required
def notifications():
    current_user = User.query.get(session['user_id'])
    if current_user.is_admin_role():
        acknowledged_notifs = Notification.query.filter_by(
            acknowledged=True
        ).order_by(Notification.created_at.desc()).all()
    else:
        acknowledged_notifs = Notification.query.filter_by(
            user_id=current_user.id,
            acknowledged=True
        ).order_by(Notification.created_at.desc()).all()
    
    return render_template('notifications.html', notifications=acknowledged_notifs, current_user=current_user)


@dashboard_bp.route('/schedule/<int:entry_id>/toggle-attendance', methods=['POST'])
@login_required
def toggle_attendance(entry_id):
    from flask import jsonify
    entry = ScheduleEntry.query.get_or_404(entry_id)
    current_user = User.query.get(session['user_id'])
    
    if current_user in entry.attendants:
        entry.attendants.remove(current_user)
        action = 'removed'
    else:
        entry.attendants.append(current_user)
        action = 'added'
        
    db.session.commit()
    return jsonify({
        'status': 'success',
        'action': action,
        'user_name': current_user.name,
        'user_id': current_user.id,
        'attendants': [u.name for u in entry.attendants]
    })


@dashboard_bp.route('/schedule/<int:entry_id>/toggle-user-attendance/<int:user_id>', methods=['POST'])
@login_required
def toggle_user_attendance(entry_id, user_id):
    from flask import jsonify
    current_user = User.query.get(session['user_id'])
    if not current_user.is_admin_role():
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
        
    entry = ScheduleEntry.query.get_or_404(entry_id)
    target_user = User.query.get_or_404(user_id)
    
    if target_user in entry.attendants:
        entry.attendants.remove(target_user)
        action = 'removed'
    else:
        entry.attendants.append(target_user)
        action = 'added'
        
    db.session.commit()
    return jsonify({
        'status': 'success',
        'action': action,
        'user_name': target_user.name,
        'user_id': target_user.id,
        'attendants': [u.name for u in entry.attendants]
    })
