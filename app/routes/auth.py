from functools import wraps
from flask import Blueprint, abort, redirect, render_template, request, jsonify, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User

bp = Blueprint('auth', __name__, url_prefix='/auth')

def role_required(role):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.rol != role:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

@bp.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('listar_dropbox.subir_archivo'))
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        nombre = request.form['nombre']
        password = request.form['password']
        rol = request.form.get('rol', 'cliente')

        if User.query.filter_by(email=email).first():
            return redirect(url_for('auth.register'))

        user = User(email=email, nombre=nombre, rol=rol)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('auth.login'))
    return render_template('register.html')