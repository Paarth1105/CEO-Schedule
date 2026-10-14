from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.models.user import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard.schedule'))
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    admin_exists = User.query.filter(User.role.ilike('admin')).first() is not None
    proprietor_exists = User.query.filter(User.role.ilike('proprietor')).first() is not None

    if request.method == 'POST':
        name = request.form['name'].strip()
        department = request.form['department'].strip()
        designation = request.form['designation'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        role = request.form.get('role', 'Employee').strip()

        # Enforce registration locking for Admin & Proprietor
        if role.lower() == 'admin' and admin_exists:
            flash('Admin registration is locked as an Admin account is already configured.', 'danger')
            return redirect(url_for('auth.register'))

        if role.lower() == 'proprietor' and proprietor_exists:
            flash('Proprietor registration is locked as a Proprietor account is already registered.', 'danger')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('auth.register'))

        user = User(name=name, department=department, designation=designation, email=email, password=password, role=role)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html', admin_exists=admin_exists, proprietor_exists=proprietor_exists)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']
        user = User.query.filter_by(email=email, password=password).first()
        if user:
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