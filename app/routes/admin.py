from datetime import datetime, date
from flask import Blueprint, request, redirect, url_for, session, flash, render_template
from app import db
from app.models.schedule import ScheduleEntry
from app.models.user import User

admin_bp = Blueprint('admin', __name__)


def parse_event_date(raw_value):
    if raw_value is None or raw_value == '':
        return date.today()
    if isinstance(raw_value, date) and not isinstance(raw_value, datetime):
        return raw_value
    if isinstance(raw_value, datetime):
        return raw_value.date()
    try:
        return datetime.strptime(raw_value, '%Y-%m-%d').date()
    except ValueError:
        return date.fromisoformat(raw_value)


def admin_required(view):
    def wrapped(*args, **kwargs):
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin_role():
            flash('Only Personal Assistant or Senior Assistant can manage schedules.', 'danger')
            return redirect(url_for('dashboard.schedule'))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


def admin_only(view):
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        user = User.query.get(session['user_id'])
        if not user or user.role != 'Admin':
            flash('Only the Admin can manage users.', 'danger')
            return redirect(url_for('dashboard.schedule'))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


@admin_bp.route('/admin/schedule/new', methods=['GET', 'POST'])
@admin_required
def new_schedule():
    users = User.query.order_by(User.name.asc()).all()
    if request.method == 'POST':
        event_date = parse_event_date(request.form['event_date'])
        start_time = request.form.get('start_hour', '').strip()
        start_minute = request.form.get('start_minute', '').strip()
        start_meridiem = request.form.get('start_meridiem', '').strip()
        end_time = request.form.get('end_hour', '').strip()
        end_minute = request.form.get('end_minute', '').strip()
        end_meridiem = request.form.get('end_meridiem', '').strip()
        start_value = f"{start_time}:{start_minute} {start_meridiem}" if start_time and start_minute else ''
        end_value = f"{end_time}:{end_minute} {end_meridiem}" if end_time and end_minute else ''
        time_value = f"{start_value} - {end_value}" if start_value and end_value else (start_value or end_value or '')
        activity = request.form['activity']
        location = request.form['location']
        responsible_person = request.form['responsible_person']
        priority = request.form['priority']
        status = request.form['status']
        remark = request.form.get('remark', '')
        reschedule = request.form.get('reschedule', 'NO')
        given_time = request.form.get('given_time', '').strip()

        entry = ScheduleEntry(event_date=event_date, time=time_value, activity=activity, location=location,
                              responsible_person=responsible_person, priority=priority, status=status,
                              remark=remark, reschedule=reschedule, given_time=given_time)
        
        attendant_ids = request.form.getlist('attendants')
        if attendant_ids:
            selected_users = User.query.filter(User.id.in_([int(uid) for uid in attendant_ids])).all()
            entry.attendants = selected_users

        db.session.add(entry)
        db.session.commit()
        flash('Schedule entry created successfully.', 'success')
        return redirect(url_for('dashboard.schedule'))

    return render_template('admin_schedule_form.html', users=users)


@admin_bp.route('/admin/schedule/<int:entry_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_schedule(entry_id):
    entry = ScheduleEntry.query.get_or_404(entry_id)
    users = User.query.order_by(User.name.asc()).all()
    if request.method == 'POST':
        entry.event_date = parse_event_date(request.form['event_date'])
        start_time = request.form.get('start_hour', '').strip()
        start_minute = request.form.get('start_minute', '').strip()
        start_meridiem = request.form.get('start_meridiem', '').strip()
        end_time = request.form.get('end_hour', '').strip()
        end_minute = request.form.get('end_minute', '').strip()
        end_meridiem = request.form.get('end_meridiem', '').strip()
        start_value = f"{start_time}:{start_minute} {start_meridiem}" if start_time and start_minute else ''
        end_value = f"{end_time}:{end_minute} {end_meridiem}" if end_time and end_minute else ''
        entry.time = f"{start_value} - {end_value}" if start_value and end_value else (start_value or end_value or entry.time)
        entry.activity = request.form['activity']
        entry.location = request.form['location']
        entry.responsible_person = request.form['responsible_person']
        entry.priority = request.form['priority']
        entry.status = request.form['status']
        entry.remark = request.form.get('remark', '')
        entry.reschedule = request.form.get('reschedule', 'NO')
        entry.given_time = request.form.get('given_time', '').strip()
        
        attendant_ids = request.form.getlist('attendants')
        selected_users = User.query.filter(User.id.in_([int(uid) for uid in attendant_ids])).all() if attendant_ids else []
        entry.attendants = selected_users

        db.session.commit()
        flash('Schedule entry updated.', 'success')
        return redirect(url_for('dashboard.schedule'))
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
        'admin_schedule_form.html',
        entry=entry,
        users=users,
        start_hour=start_hour,
        start_minute=start_minute,
        start_meridiem=start_meridiem,
        end_hour=end_hour,
        end_minute=end_minute,
        end_meridiem=end_meridiem
    )


@admin_bp.route('/admin/schedule/<int:entry_id>/delete')
@admin_required
def delete_schedule(entry_id):
    entry = ScheduleEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    flash('Schedule entry deleted.', 'success')
    return redirect(url_for('dashboard.schedule'))


@admin_bp.route('/admin/users', methods=['GET'])
@admin_only
def manage_users():
    users = User.query.order_by(User.name.asc()).all()
    return render_template('manage_users.html', users=users)


@admin_bp.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_only
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        name = request.form['name'].strip()
        department = request.form['department'].strip()
        designation = request.form['designation'].strip()
        email = request.form['email'].strip()
        password = request.form.get('password', '').strip()
        role = request.form['role']

        # Check email uniqueness
        existing = User.query.filter(User.email == email, User.id != user.id).first()
        if existing:
            flash('Email is already registered by another account.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user.id))

        user.name = name
        user.department = department
        user.designation = designation
        user.email = email
        user.role = role
        if password:
            user.password = password

        db.session.commit()
        flash('User updated successfully.', 'success')
        return redirect(url_for('admin.manage_users'))

    return render_template('admin_edit_user.html', user=user)


@admin_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_only
def delete_user(user_id):
    if session.get('user_id') == user_id:
        flash('You cannot delete your own admin account.', 'danger')
        return redirect(url_for('admin.manage_users'))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.name} has been deleted.', 'success')
    return redirect(url_for('admin.manage_users'))
