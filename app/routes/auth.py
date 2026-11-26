from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app import db
from app.constants import ALLOWED_REGISTRATION_ROLES, NEW_UNIQUE_ROLES
from app.models.user import User
from app.services.schedule_sync import (
    get_occupied_unique_roles,
    is_role_available,
    relink_position_participants_for_user,
)

auth_bp = Blueprint('auth', __name__)

_CANONICAL_ROLE_MAP = {r.lower(): r for r in ALLOWED_REGISTRATION_ROLES}


@auth_bp.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard.schedule'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    occupied_roles = get_occupied_unique_roles()
    admin_exists = 'admin' in occupied_roles
    proprietor_exists = 'proprietor' in occupied_roles

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        department = request.form.get('department', '').strip()
        designation = request.form.get('designation', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        raw_role = request.form.get('role', 'Employee').strip()
        phone_number = request.form.get('phone_number', '').strip() or None

        canonical_role = _CANONICAL_ROLE_MAP.get(raw_role.lower())
        if not canonical_role:
            flash('Invalid role selected.', 'danger')
            return redirect(url_for('auth.register'))

        if not is_role_available(canonical_role):
            flash(
                f'Registration failed: the "{canonical_role}" position is already assigned to an active account.',
                'danger',
            )
            return redirect(url_for('auth.register'))

        if User.query.filter(func.lower(User.email) == email.lower()).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('auth.register'))

        try:
            user = User(
                name=name,
                department=department,
                designation=designation,
                email=email,
                password=password,
                role=canonical_role,
                phone_number=phone_number,
                is_active=True,
            )
            db.session.add(user)
            db.session.flush()
            relink_position_participants_for_user(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                f'Registration failed: "{canonical_role}" or email "{email}" is already taken.',
                'danger',
            )
            return redirect(url_for('auth.register'))

        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template(
        'register.html',
        admin_exists=admin_exists,
        proprietor_exists=proprietor_exists,
        occupied_roles=occupied_roles,
        new_unique_roles=NEW_UNIQUE_ROLES,
    )


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter(
            func.lower(User.email) == email.lower(),
            User.password == password,
        ).first()
        if user:
            if not user.is_active:
                flash('Your account has been deactivated. Please contact the Administrator.', 'danger')
                return render_template('login.html')
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            flash('Login successful.', 'success')
            return redirect(url_for('dashboard.schedule'))
        flash('Invalid credentials.', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))
