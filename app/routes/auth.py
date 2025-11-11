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
            if not current_user.is_authenticated or not hasattr(current_user, "rol") or current_user.rol != role:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

def roles_required(*roles):
    """Decorador para requerir uno de varios roles"""
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not hasattr(current_user, "rol") or current_user.rol not in roles:
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
                
                # Log de actividad
                activity_log = UserActivityLog(
                    user_id=user.id,
                    accion='login',
                    ip_address=request.remote_addr
                )
                db.session.add(activity_log)
                db.session.commit()
                
                # Verificar si hay una URL de destino (next parameter)
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/'):
                    # Solo redirigir si es una URL relativa y segura
                    return redirect(next_page)
                
                # Redirigir según el rol
                if user.rol == 'cliente':
                    return redirect(url_for('listar_dropbox.subir_archivo'))
                else:
                    # Admin, superadmin y lector van al dashboard admin
                    return redirect(url_for('main.dashboard_admin'))
        else:
            error = "Credenciales incorrectas."
    
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
    # Si el usuario ya está autenticado, redirigir al dashboard
    if current_user.is_authenticated:
        flash('Ya tienes una cuenta activa. Si necesitas crear otra cuenta, cierra sesión primero.', 'info')
        if current_user.rol == 'cliente':
            return redirect(url_for('listar_dropbox.subir_archivo'))
        else:
            return redirect(url_for('main.dashboard'))
    
    from forms import ClienteRegistrationForm
    from app.utils.countries import get_countries_list, get_nationalities_list
    
    form = ClienteRegistrationForm()
    errors = {}
    
    # Obtener listas de países y nacionalidades
    countries = get_countries_list()
    nationalities = get_nationalities_list()
    
    # Configurar las opciones del formulario
    form.nationality.choices = [('', 'Selecciona tu nacionalidad')] + nationalities
    form.country.choices = [('', 'Selecciona tu país')] + [(code, country) for code, country in countries]
    
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                # Normalización básica
                email = (form.email.data or '').strip().lower()
                telefono = (form.telephone.data or '').strip()
                document_number = (form.document_number.data or '').strip().upper()
                
                # Validaciones estrictas para evitar registros duplicados
                existing_user_email = User.query.filter_by(email=email).first()
                if existing_user_email:
                    errors['email'] = 'Este correo electrónico ya está registrado. Si ya tienes una cuenta, inicia sesión en lugar de registrarte nuevamente.'
                    flash('Este correo electrónico ya está registrado. Por favor, inicia sesión si ya tienes una cuenta.', 'error')
                    raise ValueError('duplicate_email')
                
                if telefono:
                    existing_user_phone = User.query.filter_by(telefono=telefono).first()
                    if existing_user_phone:
                        errors['telephone'] = 'Este número de teléfono ya está registrado. Si ya tienes una cuenta, inicia sesión.'
                        flash('Este número de teléfono ya está registrado. Por favor, inicia sesión si ya tienes una cuenta.', 'error')
                        raise ValueError('duplicate_phone')
                
                if document_number:
                    existing_user_doc = User.query.filter_by(document_number=document_number).first()
                    if existing_user_doc:
                        errors['document_number'] = 'Este número de documento ya está registrado. Si ya tienes una cuenta, inicia sesión.'
                        flash('Este número de documento ya está registrado. Por favor, inicia sesión si ya tienes una cuenta.', 'error')
                        raise ValueError('duplicate_doc')
                
                # Validación adicional: verificar si hay un usuario con el mismo nombre y apellido Y mismo documento
                # (esto ayuda a detectar intentos de registro duplicado con datos similares)
                nombre = (form.name.data or '').strip()
                apellido = (form.lastname.data or '').strip()
                if nombre and apellido and document_number:
                    existing_similar = User.query.filter(
                        User.nombre.ilike(f'%{nombre}%'),
                        User.apellido.ilike(f'%{apellido}%'),
                        User.document_number == document_number
                    ).first()
                    if existing_similar:
                        errors['general'] = 'Ya existe una cuenta con información similar (mismo nombre y documento). Si ya te registraste, por favor inicia sesión.'
                        flash('Ya existe una cuenta con información similar. Si ya te registraste, por favor inicia sesión.', 'error')
                        raise ValueError('duplicate_user')
                # Crear el usuario cliente
                user = User(
                    email=email,
                    nombre=form.name.data,
                    apellido=form.lastname.data,
                    telefono=telefono,
                    ciudad=form.city.data,
                    estado=form.state.data,
                    direccion=form.address.data,
                    codigo_postal=form.zip_code.data,
                    document_type=form.document_type.data,
                    document_number=document_number,
                    nacionality=form.nationality.data,
                    country=dict(countries)[form.country.data] if form.country.data else None,  # Usar nombre del país
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
                    
                    # SINCRONIZACIÓN: Crear entrada de carpeta raíz en la BD después de obtener el user.id
                    from app.models import Folder
                    carpeta_raiz = Folder(
                        name=user.email.split('@')[0],  # Usar parte del email como nombre
                        user_id=user.id,
                        dropbox_path=path,
                        es_publica=True
                    )
                    db.session.add(carpeta_raiz)
                    print(f"INFO | Carpeta raíz creada en BD para cliente registrado {user.id}: {path}")
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
                if str(e) in ['duplicate_email', 'duplicate_phone', 'duplicate_doc', 'duplicate_user']:
                    # Los errores ya fueron manejados arriba con flash y errors
                    pass
                else:
                    errors['general'] = f"Error al crear la cuenta: {str(e)}"
                    flash(f"Error al crear la cuenta: {str(e)}", 'error')
        else:
            # Errores de validación del formulario
            for field, field_errors in form.errors.items():
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
        document_type = (request.form.get('document_type') or '').strip()
        document_number = (request.form.get('document_number') or '').strip()
        
        # DEBUG: Ver exactamente qué datos llegan del formulario en add_beneficiary
        print(f"🔍 DEBUG add_beneficiary - Datos recibidos:")
        print(f"   nombre: {repr(nombre)}")
        print(f"   email: {repr(email)}")
        print(f"   fecha_nacimiento: {repr(fecha_nacimiento)}")
        print(f"   document_type: {repr(document_type)}")
        print(f"   document_number: {repr(document_number)}")
        print(f"   request.form completo: {dict(request.form)}")
        print(f"   request.method: {request.method}")
        
        # Nota: se permite cualquier nombre de beneficiario, incluyendo los que comiencen por 'Beneficiario'
        
        if nombre and email and document_type and document_number:
            try:
                beneficiario = Beneficiario(
                    nombre=nombre,
                    email=email,
                    fecha_nacimiento=datetime.strptime(fecha_nacimiento, '%Y-%m-%d').date() if fecha_nacimiento else None,
                    titular_id=user.id,
                    document_type=document_type,
                    document_number=document_number
                )
                
                # Primero guardar para asegurar que beneficiario.id no sea None
                db.session.add(beneficiario)
                db.session.commit()
                
                # Crear carpeta en Dropbox para el beneficiario usando solo el nombre (sin ID)
                try:
                    from app.dropbox_utils import create_dropbox_folder
                    path_ben = f"{user.dropbox_folder_path}/{nombre}"
                    create_dropbox_folder(path_ben)
                    beneficiario.dropbox_folder_path = path_ben
                    db.session.commit()
                except Exception as e:
                    print(f"Error creando carpeta Dropbox para beneficiario: {e}")
                    # No crítico: la creación del beneficiario ya fue confirmada
                
                flash(f'Beneficiario {nombre} agregado exitosamente.', 'success')
                
            except Exception as e:
                db.session.rollback()
                flash(f'Error al agregar beneficiario: {str(e)}', 'error')
        else:
            if request.method == 'POST':
                flash('Todos los campos son obligatorios (incluye documento).', 'error')
    
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
    return redirect(url_for('auth.login'))

@bp.route('/register/complete', methods=['GET', 'POST'])
def complete_registration():
    """Completar registro - redirigir a login"""
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

@bp.route('/admin/change-user-password/<int:user_id>', methods=['POST'])
@login_required
@roles_required('admin', 'superadmin')
def change_user_password(user_id):
    """Cambiar contraseña de otro usuario (solo administradores)"""
    user = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not new_password or not confirm_password:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "error": "Todos los campos son requeridos."})
        flash('Todos los campos son requeridos.', 'error')
        return redirect(url_for('usuarios.lista_usuarios'))
    
    if new_password != confirm_password:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "error": "Las contraseñas no coinciden."})
        flash('Las contraseñas no coinciden.', 'error')
        return redirect(url_for('usuarios.lista_usuarios'))
    
    if len(new_password) < 6:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "error": "La contraseña debe tener al menos 6 caracteres."})
        flash('La contraseña debe tener al menos 6 caracteres.', 'error')
        return redirect(url_for('usuarios.lista_usuarios'))
    
    try:
        user.set_password(new_password)
        db.session.commit()
        
        # Registrar actividad
        registrar_actividad(current_user, 'password_changed', f'Contraseña cambiada para el usuario {user.email}')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": True, "message": "Contraseña actualizada correctamente."})
        
        flash('Contraseña actualizada correctamente.', 'success')
        return redirect(url_for('usuarios.lista_usuarios'))
        
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "error": f"Error al actualizar contraseña: {str(e)}"})
        flash(f'Error al actualizar contraseña: {str(e)}', 'error')
        return redirect(url_for('usuarios.lista_usuarios'))

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

@bp.route('/check-email', methods=['POST'])
def check_email():
    """Verificar si un correo está registrado.

    Espera JSON con:
    - email: str
    """
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').strip().lower()

        if not email:
            return jsonify({'success': False, 'exists': False, 'message': 'Email requerido.'}), 200

        user = User.query.filter_by(email=email).first()
        return jsonify({'success': True, 'exists': bool(user)})
    except Exception as e:
        current_app.logger.exception(f"Error en check-email: {e}")
        return jsonify({'success': False, 'exists': False, 'message': 'Error interno del servidor.'}), 200

@bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Restablecer contraseña vía JSON (usado desde la pantalla de login).

    Espera JSON con:
    - email: str
    - nueva_contrasena: str
    """
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').strip().lower()
        nueva_contrasena = data.get('nueva_contrasena')

        if not email or not nueva_contrasena:
            return jsonify({
                'success': False,
                'message': 'Email y nueva contraseña son requeridos.'
            }), 400

        if len(nueva_contrasena) < 6:
            return jsonify({
                'success': False,
                'message': 'La nueva contraseña debe tener al menos 6 caracteres.'
            }), 400

        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({
                'success': False,
                'message': 'Usuario no encontrado.'
            }), 404

        user.set_password(nueva_contrasena)
        db.session.commit()

        # Registrar actividad del usuario afectado
        try:
            registrar_actividad(user, 'password_reset', 'Contraseña restablecida desde la pantalla de login')
        except Exception:
            # No bloquear por errores de logging
            pass

        return jsonify({'success': True, 'message': 'Contraseña actualizada correctamente.'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Error en reset-password: {e}")
        return jsonify({'success': False, 'message': 'Error interno del servidor.'}), 500