from functools import wraps
from flask import Blueprint, abort, redirect, render_template, request, jsonify, url_for, flash, current_app, session
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from app import db
from app.models import Beneficiario, User, UserActivityLog
from forms import LoginForm, BeneficiarioForm
import logging

# Configurar logging
logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__, url_prefix='/auth')

def role_required(role):
    """Decorador para requerir un rol específico"""
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.rol != role:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

def roles_required(*roles):
    """Decorador para requerir uno de varios roles"""
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.rol not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

def registrar_actividad(user, accion, descripcion=None):
    """Helper para registrar actividad de usuario"""
    actividad = UserActivityLog(
        user_id=user.id,
        accion=accion,
        descripcion=descripcion,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:255]
    )
    db.session.add(actividad)
    db.session.commit()

@bp.route('/', methods=['GET', 'POST'])
def login():
    # Redirigir si ya está logueado
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    error = None
    
    if form.validate_on_submit():
        email = form.username.data
        password = form.password.data
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if not user.activo:
                error = "Tu cuenta está desactivada. Contacta al administrador."
            else:
                # Actualizar último acceso
                user.ultimo_acceso = datetime.utcnow()
                db.session.commit()
                
                # Login exitoso
                login_user(user, remember=True)
                
                # Registrar actividad
                registrar_actividad(user, 'login', f'Inicio de sesión desde {request.remote_addr}')
                
                # Redirigir según el rol
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                elif user.es_cliente():
                    return redirect(url_for('listar_dropbox.carpetas_dropbox'))
                elif user.puede_administrar():
                    return redirect(url_for('main.dashboard_admin'))
                elif user.es_lector():
                    return redirect(url_for('main.listar_carpetas'))
                else:
                    return redirect(url_for('main.dashboard_lector'))
        else:
            error = "Credenciales incorrectas."
            
            # Registrar intento de login fallido
            if user:
                registrar_actividad(user, 'login_failed', f'Intento de login fallido desde {request.remote_addr}')
    elif request.method == 'POST':
        logger.error(f"Form validation failed: {form.errors}")
        error = "Por favor, completa todos los campos correctamente."
    
    return render_template('login.html', form=form, error=error)

@bp.route('/login_direct')
def login_direct():
    """Ruta alternativa para /auth sin redirección"""
    return login()

@bp.route('/logout')
@login_required
def logout():
    # Registrar logout
    registrar_actividad(current_user, 'logout', f'Cierre de sesión desde {request.remote_addr}')
    
    logout_user()
    return redirect(url_for('auth.login'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """Página de registro de clientes"""
    from forms import ClienteRegistrationForm
    
    form = ClienteRegistrationForm()
    errors = {}
    
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                # Crear el usuario cliente
                user = User(
                    email=form.email.data,
                    nombre=form.name.data,
                    apellido=form.lastname.data,
                    telefono=form.telephone.data,
                    ciudad=form.city.data,
                    estado=form.state.data,
                    direccion=form.address.data,
                    codigo_postal=form.zip_code.data,
                    fecha_nacimiento=form.date_of_birth.data,
                    rol='cliente',
                    activo=True,
                    fecha_registro=datetime.utcnow()
                )
                user.set_password(form.password.data)
                
                db.session.add(user)
                db.session.commit()
                
                # Crear carpeta en Dropbox para el usuario
                try:
                    from app.dropbox_utils import create_dropbox_folder
                    path = f"/{user.email}"
                    create_dropbox_folder(path)
                    user.dropbox_folder_path = path
                    db.session.commit()
                except Exception as e:
                    # Si falla la creación de carpeta, no es crítico
                    print(f"Error creando carpeta Dropbox: {e}")
                
                # Registrar actividad
                user.registrar_actividad('user_registered', f'Cliente registrado desde {request.remote_addr}')
                
                # Mostrar modal de confirmación para agregar beneficiarios
                return render_template('register.html', 
                                    form=form, 
                                    errors=errors, 
                                    show_beneficiary_modal=True,
                                    user_id=user.id)
                
            except Exception as e:
                db.session.rollback()
                errors['general'] = f"Error al crear la cuenta: {str(e)}"
        else:
            # Errores de validación del formulario
            for field, field_errors in form.errors.items():
                if field == 'csrf_token':
                    continue
                field_name = getattr(form, field).label.text
                errors[field] = f"{field_name}: {', '.join(field_errors)}"
    
    return render_template('register.html', form=form, errors=errors)

@bp.route('/register/add_beneficiary/<int:user_id>', methods=['GET', 'POST'])
def add_beneficiary(user_id):
    """Agregar beneficiarios al usuario registrado"""
    user = User.query.get_or_404(user_id)
    form = BeneficiarioForm()
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        fecha_nacimiento = request.form.get('fecha_nacimiento')
        
        if nombre and email:
            try:
                beneficiario = Beneficiario(
                    nombre=nombre,
                    email=email,
                    fecha_nacimiento=datetime.strptime(fecha_nacimiento, '%Y-%m-%d').date() if fecha_nacimiento else None,
                    titular_id=user.id
                )
                
                # Crear carpeta en Dropbox para el beneficiario
                try:
                    from app.dropbox_utils import create_dropbox_folder
                    path_ben = f"{user.dropbox_folder_path}/{nombre}_{beneficiario.id}"
                    create_dropbox_folder(path_ben)
                    beneficiario.dropbox_folder_path = path_ben
                except Exception as e:
                    print(f"Error creando carpeta Dropbox para beneficiario: {e}")
                
                db.session.add(beneficiario)
                db.session.commit()
                
                flash(f'Beneficiario {nombre} agregado exitosamente.', 'success')
                
            except Exception as e:
                db.session.rollback()
                flash(f'Error al agregar beneficiario: {str(e)}', 'error')
    
    # Obtener beneficiarios existentes
    beneficiarios = Beneficiario.query.filter_by(titular_id=user.id).all()
    
    return render_template('add_beneficiaries.html', 
                        user=user, 
                        beneficiarios=beneficiarios,
                        form=form)

@bp.route('/register/complete_with_beneficiaries/<int:user_id>', methods=['POST'])
def complete_with_beneficiaries(user_id):
    """Completar registro con beneficiarios y redirigir a login"""
    user = User.query.get_or_404(user_id)
    user.registrar_actividad('registration_completed', 'Registro completado con beneficiarios')
    flash('Registro completado exitosamente. Ya puedes iniciar sesión.', 'success')
    return redirect(url_for('auth.login'))

@bp.route('/register/complete', methods=['POST'])
def complete_registration():
    """Completar registro - redirigir a login"""
    flash('Usuario creado exitosamente. Ya puedes iniciar sesión.', 'success')
    return redirect(url_for('auth.login'))

@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Cambiar contraseña del usuario actual"""
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if not current_user.check_password(current_password):
            flash('La contraseña actual es incorrecta.', 'error')
        elif new_password != confirm_password:
            flash('Las contraseñas nuevas no coinciden.', 'error')
        elif len(new_password) < 6:
            flash('La nueva contraseña debe tener al menos 6 caracteres.', 'error')
        else:
            current_user.set_password(new_password)
            db.session.commit()
            
            # Registrar actividad
            registrar_actividad(current_user, 'password_changed', 'Contraseña cambiada por el usuario')
            
            flash('Contraseña actualizada correctamente.', 'success')
            return redirect(url_for('main.profile'))
    
    return render_template('auth/change_password.html')

@bp.route('/admin/toggle-user-status/<int:user_id>')
@login_required
@roles_required('admin', 'superadmin')
def toggle_user_status(user_id):
    """Activar/Desactivar usuario"""
    user = User.query.get_or_404(user_id)
    
    # Solo superadmin puede desactivar otros admin/superadmin
    if user.rol in ['admin', 'superadmin'] and not current_user.es_superadmin():
        abort(403)
    
    user.activo = not user.activo
    db.session.commit()
    
    # Registrar actividad
    estado = 'activado' if user.activo else 'desactivado'
    registrar_actividad(current_user, 'user_status_changed', f'Usuario {user.email} {estado}')
    
    flash(f'Usuario {estado} correctamente.', 'success')
    return redirect(url_for('main.listar_usuarios_admin'))

@bp.route('/admin/change-user-role/<int:user_id>', methods=['POST'])
@login_required
@role_required('superadmin')
def change_user_role(user_id):
    """Cambiar rol de usuario (solo superadmin)"""
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('new_role')
    
    roles_validos = ['cliente', 'lector', 'admin', 'superadmin']
    if new_role not in roles_validos:
        flash('Rol inválido.', 'error')
        return redirect(url_for('main.listar_usuarios_admin'))
    
    old_role = user.rol
    user.rol = new_role
    db.session.commit()
    
    # Registrar actividad
    registrar_actividad(current_user, 'user_role_changed', f'Rol de {user.email} cambiado de {old_role} a {new_role}')
    
    flash(f'Rol actualizado a {new_role}.', 'success')
    return redirect(url_for('main.listar_usuarios_admin'))