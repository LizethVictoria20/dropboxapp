from flask import Blueprint, redirect, render_template, request, jsonify, current_app, url_for, flash
from app import db
from app.models import Beneficiario, User, UserActivityLog
from app.dropbox_utils import create_dropbox_folder
from app.routes.listar_dropbox import obtener_estructura_dropbox
import dropbox
from datetime import datetime
import json

bp = Blueprint('users', __name__, url_prefix='/users')

@bp.route('/create', methods=['POST'])
def create_user():
    email = request.json.get('email')
    password = request.json.get('password')
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Usuario ya existe'}), 400

    user = User(email=email, password=password)
    db.session.add(user)
    db.session.commit()

    # Crea carpeta en Dropbox
    path = f"/{email}"
    create_dropbox_folder(path)
    user.dropbox_folder_path = path
    db.session.commit()
    return jsonify({'message': 'Usuario y carpeta creados'}), 201


@bp.route("/crear_beneficiario", methods=["GET", "POST"])
def crear_beneficiario():
    titulares = User.query.filter_by(es_beneficiario=False).all()
    if request.method == "POST":
        nombre = request.form.get("nombre")
        email = request.form.get("email")
        fecha_nac = request.form.get("fecha_nacimiento")
        titular_id = request.form.get("titular_id")
        # Validaciones aquí...

        beneficiario = Beneficiario(
            nombre=nombre,
            email=email,
            fecha_nacimiento=fecha_nac,
            titular_id=titular_id
        )
        db.session.add(beneficiario)
        db.session.commit()
        # Crea carpeta en Dropbox dentro del titular
        titular = User.query.get(titular_id)
        path_ben = f"{titular.dropbox_folder_path}/{nombre}_{beneficiario.id}"
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        dbx.files_create_folder_v2(path_ben)
        beneficiario.dropbox_folder_path = path_ben
        db.session.commit()
        return redirect(url_for("users.crear_beneficiario"))
    return render_template("crear_beneficiario.html", titulares=titulares)


@bp.route("/listar_beneficiarios")
def listar_beneficiarios():
    titulares = User.query.filter_by(es_beneficiario=False).all()
    estructuras_titulares = {}
    estructuras_beneficiarios = {}

    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
    for titular in titulares:
        estructuras_titulares[titular.id] = obtener_estructura_dropbox(path=titular.dropbox_folder_path)
        for ben in titular.beneficiarios:
            estructuras_beneficiarios[ben.id] = obtener_estructura_dropbox(path=ben.dropbox_folder_path)

    return render_template(
        "listar_beneficiarios.html",
        titulares=titulares,
        estructuras_titulares=estructuras_titulares,
        estructuras_beneficiarios=estructuras_beneficiarios
    )


@bp.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    """Vista para crear usuarios con selección de roles y permisos adicionales"""
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            email = request.form.get('email')
            password = request.form.get('password')
            nombre = request.form.get('nombre')
            apellido = request.form.get('apellido')
            telefono = request.form.get('telefono')
            ciudad = request.form.get('ciudad')
            estado = request.form.get('estado')
            direccion = request.form.get('direccion')
            codigo_postal = request.form.get('codigo_postal')
            fecha_nacimiento_str = request.form.get('fecha_nacimiento')
            nacionality = request.form.get('nacionality')
            country = request.form.get('country')
            rol = request.form.get('rol')
            
            # Validaciones básicas
            if not email or not password:
                flash('Email y contraseña son obligatorios', 'error')
                return redirect(url_for('users.listar_usuarios'))
            
            # Verificar si el usuario ya existe
            if User.query.filter_by(email=email).first():
                flash('El email ya está registrado', 'error')
                return redirect(url_for('users.listar_usuarios'))
            
            # Crear el usuario
            user = User(
                email=email,
                nombre=nombre,
                apellido=apellido,
                telefono=telefono,
                ciudad=ciudad,
                estado=estado,
                direccion=direccion,
                codigo_postal=codigo_postal,
                nacionality=nacionality,
                country=country,
                rol=rol
            )
            
            # Establecer contraseña
            user.set_password(password)
            
            # Procesar fecha de nacimiento
            if fecha_nacimiento_str:
                try:
                    fecha_nacimiento = datetime.strptime(fecha_nacimiento_str, '%Y-%m-%d').date()
                    user.fecha_nacimiento = fecha_nacimiento
                except ValueError:
                    flash('Formato de fecha de nacimiento inválido', 'error')
                    return redirect(url_for('users.listar_usuarios'))
            
            # Procesar permisos adicionales para lectores
            if rol == 'lector':
                permisos_adicionales = []
                if request.form.get('puede_renombrar'):
                    permisos_adicionales.append('renombrar')
                if request.form.get('puede_mover'):
                    permisos_adicionales.append('mover')
                if request.form.get('puede_eliminar'):
                    permisos_adicionales.append('eliminar')
                if request.form.get('puede_agregar_beneficiarios'):
                    permisos_adicionales.append('agregar_beneficiarios')
                
                user.lector_extra_permissions = json.dumps(permisos_adicionales)
            
            # Crear carpeta en Dropbox
            try:
                path = f"/{email}"
                create_dropbox_folder(path)
                user.dropbox_folder_path = path
            except Exception as e:
                flash(f'Error al crear carpeta en Dropbox: {str(e)}', 'warning')
            
            # Guardar usuario en la base de datos
            db.session.add(user)
            db.session.commit()
            
            # Registrar la actividad de creación de usuario
            from .utils.activity_logger import log_user_activity
            log_user_activity(
                user_id=user.id,
                accion='create_user',
                descripcion=f'Usuario creado con rol {rol}'
            )
            
            flash(f'Usuario {user.nombre_completo} creado exitosamente con rol {rol}', 'success')
            return redirect(url_for('users.listar_usuarios'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear usuario: {str(e)}', 'error')
            return redirect(url_for('users.listar_usuarios'))
    
    # GET request - redirigir al listado (el modal se maneja en el frontend)
    return redirect(url_for('users.listar_usuarios'))

@bp.route('/listar_usuarios')
def listar_usuarios():
    """Vista para listar usuarios con paginación"""
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Mostrar 10 usuarios por página
    
    # Obtener usuarios paginados (excluyendo clientes)
    pagination = User.query.filter(User.rol != 'cliente').paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    usuarios = pagination.items
    
    return render_template('listar_usuarios.html', 
                         usuarios=usuarios, 
                         pagination=pagination)

@bp.route('/get_user/<int:user_id>')
def get_user(user_id):
    """Obtener datos de un usuario específico"""
    try:
        user = User.query.get(user_id)
        if user:
            user_data = {
                'id': user.id,
                'email': user.email,
                'nombre': user.nombre,
                'apellido': user.apellido,
                'telefono': user.telefono,
                'ciudad': user.ciudad,
                'estado': user.estado,
                'direccion': user.direccion,
                'codigo_postal': user.codigo_postal,
                'nacionality': user.nacionality,
                'country': user.country,
                'fecha_nacimiento': user.fecha_nacimiento.strftime('%Y-%m-%d') if user.fecha_nacimiento else None,
                'rol': user.rol,
                'activo': user.activo,
                'fecha_registro': user.fecha_registro.strftime('%d/%m/%Y') if user.fecha_registro else None,
                'lector_extra_permissions': user.lector_extra_permissions
            }
            return jsonify({'success': True, 'user': user_data})
        else:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/update_user', methods=['POST'])
def update_user():
    """Actualizar datos de un usuario"""
    try:
        user_id = request.form.get('user_id')
        user = User.query.get(user_id)
        
        if not user:
            flash('Usuario no encontrado', 'error')
            return redirect(url_for('users.listar_usuarios'))
        
        # Actualizar datos básicos
        user.email = request.form.get('email')
        user.nombre = request.form.get('nombre')
        user.apellido = request.form.get('apellido')
        user.telefono = request.form.get('telefono')
        user.ciudad = request.form.get('ciudad')
        user.estado = request.form.get('estado')
        user.direccion = request.form.get('direccion')
        user.codigo_postal = request.form.get('codigo_postal')
        user.nacionality = request.form.get('nacionality')
        user.country = request.form.get('country')
        user.rol = request.form.get('rol')
        
        # Procesar permisos adicionales para lectores
        if user.rol == 'lector':
            permisos_adicionales = []
            if request.form.get('puede_renombrar'):
                permisos_adicionales.append('renombrar')
            if request.form.get('puede_mover'):
                permisos_adicionales.append('mover')
            if request.form.get('puede_eliminar'):
                permisos_adicionales.append('eliminar')
            if request.form.get('puede_agregar_beneficiarios'):
                permisos_adicionales.append('agregar_beneficiarios')
            
            user.lector_extra_permissions = json.dumps(permisos_adicionales) if permisos_adicionales else None
        else:
            # Limpiar permisos si no es lector
            user.lector_extra_permissions = None
        
        # Procesar fecha de nacimiento
        fecha_nacimiento_str = request.form.get('fecha_nacimiento')
        if fecha_nacimiento_str:
            try:
                fecha_nacimiento = datetime.strptime(fecha_nacimiento_str, '%Y-%m-%d').date()
                user.fecha_nacimiento = fecha_nacimiento
            except ValueError:
                flash('Formato de fecha de nacimiento inválido', 'error')
                return redirect(url_for('users.listar_usuarios'))
        
        # Verificar email único
        existing_user = User.query.filter(User.email == user.email, User.id != user.id).first()
        if existing_user:
            flash('El email ya está registrado por otro usuario', 'error')
            return redirect(url_for('users.listar_usuarios'))
        
        db.session.commit()
        
        # Registrar la actividad de actualización
        from .utils.activity_logger import log_profile_update
        log_profile_update(
            user_id=user.id,
            fields_updated=['email', 'nombre', 'apellido', 'telefono', 'ciudad', 'estado', 'direccion', 'codigo_postal', 'nacionality', 'country', 'rol', 'activo', 'fecha_nacimiento']
        )
        
        flash(f'Usuario {user.nombre_completo} actualizado exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar usuario: {str(e)}', 'error')
    
    return redirect(url_for('users.listar_usuarios'))

@bp.route('/get_user_history/<int:user_id>')
def get_user_history(user_id):
    """Obtener historial de actividades de un usuario específico desde la base de datos"""
    try:
        # Obtener usuario
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        
        # Datos básicos del usuario
        user_data = {
            'id': user.id,
            'email': user.email,
            'nombre': user.nombre,
            'apellido': user.apellido,
            'rol': user.rol
        }
        
        # Obtener actividades
        activities = UserActivityLog.query.filter_by(user_id=user_id)\
            .order_by(UserActivityLog.fecha.desc())\
            .limit(50)\
            .all()
        
        history = []
        
        # Procesar actividades
        for activity in activities:
            # Mapear acciones
            tipo_mapping = {
                'login': 'login',
                'logout': 'logout',
                'upload_file': 'file_upload',
                'delete_file': 'file_delete',
                'rename_file': 'file_rename',
                'move_file': 'file_move',
                'update_profile': 'user_update',
                'add_beneficiary': 'beneficiary_add',
                'remove_beneficiary': 'beneficiary_remove',
                'change_permissions': 'permission_change',
                'create_folder': 'system',
                'delete_folder': 'system',
                'activate_user': 'system',
                'deactivate_user': 'system',
                'create_user': 'system',
                'create_beneficiario': 'beneficiary_add',
                'change_password': 'system',
                'login_failed': 'system'
            }
            
            tipo = tipo_mapping.get(activity.accion, 'system')
            
            # Generar título
            titulo_mapping = {
                'login': 'Inicio de sesión',
                'logout': 'Cierre de sesión',
                'upload_file': 'Subida de archivo',
                'delete_file': 'Eliminación de archivo',
                'rename_file': 'Renombrado de archivo',
                'move_file': 'Movimiento de archivo',
                'update_profile': 'Actualización de perfil',
                'add_beneficiary': 'Agregar beneficiario',
                'remove_beneficiary': 'Eliminar beneficiario',
                'change_permissions': 'Cambio de permisos',
                'create_folder': 'Creación de carpeta',
                'delete_folder': 'Eliminación de carpeta',
                'activate_user': 'Activación de usuario',
                'deactivate_user': 'Desactivación de usuario',
                'create_user': 'Creación de cuenta',
                'create_beneficiario': 'Creación de beneficiario',
                'change_password': 'Cambio de contraseña',
                'login_failed': 'Intento de inicio de sesión fallido'
            }
            
            titulo = titulo_mapping.get(activity.accion, 'Actividad del sistema')
            
            # Formatear fecha
            fecha_str = "N/A"
            if activity.fecha:
                try:
                    fecha_str = activity.fecha.strftime("%d/%m/%Y %H:%M")
                except:
                    fecha_str = str(activity.fecha)
            
            history.append({
                'tipo': tipo,
                'titulo': titulo,
                'descripcion': activity.descripcion or f'Acción: {activity.accion}',
                'fecha': fecha_str,
                'ip_address': activity.ip_address,
                'user_agent': activity.user_agent
            })
        
        # Si no hay actividades, agregar información básica
        if not history:
            fecha_registro = "N/A"
            if user.fecha_registro:
                try:
                    fecha_registro = user.fecha_registro.strftime("%d/%m/%Y %H:%M")
                except:
                    fecha_registro = str(user.fecha_registro)
            
            history.append({
                'tipo': 'system',
                'titulo': 'Creación de cuenta',
                'descripcion': 'Se creó la cuenta del usuario en el sistema',
                'fecha': fecha_registro
            })
            
            if user.ultimo_acceso:
                fecha_ultimo = "N/A"
                try:
                    fecha_ultimo = user.ultimo_acceso.strftime("%d/%m/%Y %H:%M")
                except:
                    fecha_ultimo = str(user.ultimo_acceso)
                
                history.append({
                    'tipo': 'login',
                    'titulo': 'Último acceso',
                    'descripcion': f'Último inicio de sesión registrado',
                    'fecha': fecha_ultimo
                })
        
        # Agregar información de permisos para lectores
        if user.rol == 'lector' and user.lector_extra_permissions:
            try:
                permissions = json.loads(user.lector_extra_permissions)
                if permissions:
                    has_permission_activity = any(
                        'permission_change' in h.get('tipo', '') for h in history
                    )
                    
                    if not has_permission_activity:
                        fecha_registro = "N/A"
                        if user.fecha_registro:
                            try:
                                fecha_registro = user.fecha_registro.strftime("%d/%m/%Y %H:%M")
                            except:
                                fecha_registro = str(user.fecha_registro)
                        
                        history.append({
                            'tipo': 'permission_change',
                            'titulo': 'Configuración de permisos',
                            'descripcion': f'Se configuraron permisos adicionales: {", ".join(permissions)}',
                            'fecha': fecha_registro
                        })
            except:
                pass
        
        return jsonify({
            'success': True, 
            'user': user_data, 
            'history': history
        })
        
    except Exception as e:
        print(f"Error en get_user_history: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
