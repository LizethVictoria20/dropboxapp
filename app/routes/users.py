from flask import Blueprint, redirect, render_template, request, jsonify, current_app, url_for, flash
from flask_login import login_required, current_user
from app import db
from sqlalchemy import or_
from app.models import Beneficiario, User, UserActivityLog, Archivo, Folder
from app.dropbox_utils import create_dropbox_folder
from app.routes.listar_dropbox import obtener_estructura_dropbox
import dropbox
from datetime import datetime
import json

from app.dropbox_utils import get_dbx
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
    """Crear beneficiario - maneja tanto formularios normales como AJAX"""
    
    # Verificar si el usuario está autenticado
    if not current_user.is_authenticated:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': 'Debes iniciar sesión para realizar esta acción',
                'redirect': url_for('auth.login')
            }), 401
        else:
            flash("Debes iniciar sesión para realizar esta acción", "error")
            return redirect(url_for("auth.login"))
    
    # Verificar permisos: admin, superadmin o lector con permiso específico
    if not (current_user.puede_administrar() or current_user.puede_agregar_beneficiarios()):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': 'No tienes permisos para agregar beneficiarios'
            }), 403
        else:
            flash("No tienes permisos para agregar beneficiarios", "error")
            return redirect(url_for("main.dashboard"))
    
    titulares = User.query.filter_by(es_beneficiario=False).all()
    
    if request.method == "POST":
        try:
            nombre = request.form.get("nombre")
            email = request.form.get("email")
            fecha_nac = request.form.get("fecha_nacimiento")
            titular_id = request.form.get("titular_id")
            document_type = (request.form.get("document_type") or '').strip()
            document_number = (request.form.get("document_number") or '').strip()
            
            # DEBUG: Ver exactamente qué datos llegan del formulario
            print(f"🔍 DEBUG crear_beneficiario - Datos recibidos:")
            print(f"   nombre: {repr(nombre)}")
            print(f"   email: {repr(email)}")
            print(f"   fecha_nac: {repr(fecha_nac)}")
            print(f"   titular_id: {repr(titular_id)}")
            print(f"   request.form completo: {dict(request.form)}")
            print(f"   Headers: {dict(request.headers)}")
            
            # Validaciones básicas
            if not nombre or not email or not titular_id or not document_type or not document_number:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False, 
                        'error': 'Todos los campos son obligatorios'
                    }), 400
                else:
                    flash("Todos los campos son obligatorios", "error")
                    return redirect(url_for("users.crear_beneficiario"))
            
            # Nota: se permite cualquier nombre de beneficiario, incluyendo los que comiencen por 'Beneficiario'
            
            # Verificar que el titular existe
            titular = User.query.get(titular_id)
            if not titular:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False, 
                        'error': 'Titular no encontrado'
                    }), 404
                else:
                    flash("Titular no encontrado", "error")
                    return redirect(url_for("users.crear_beneficiario"))
            
            # Procesar fecha de nacimiento
            fecha_nacimiento = None
            if fecha_nac:
                try:
                    from datetime import datetime
                    fecha_nacimiento = datetime.strptime(fecha_nac, '%Y-%m-%d').date()
                except ValueError:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({
                            'success': False, 
                            'error': 'Formato de fecha de nacimiento inválido'
                        }), 400
                    else:
                        flash("Formato de fecha de nacimiento inválido", "error")
                        return redirect(url_for("users.crear_beneficiario"))
            
            # Crear beneficiario de manera simple
            print(f"🔍 Creando beneficiario: {nombre} ({email}) para titular {titular_id}")
            from app.utils.beneficiario_utils import create_beneficiario_simple
            result = create_beneficiario_simple(
                nombre=nombre,
                email=email,
                fecha_nacimiento=fecha_nacimiento,
                titular_id=int(titular_id),
                document_type=document_type,
                document_number=document_number
            )
            
            print(f"📋 Resultado de crear beneficiario: {result}")
            
            if result['success']:
                # Debug: Verificar headers
                print(f"🔍 Headers de la petición:")
                print(f"   X-Requested-With: {request.headers.get('X-Requested-With')}")
                print(f"   Content-Type: {request.headers.get('Content-Type')}")
                print(f"   User-Agent: {request.headers.get('User-Agent')}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    response_data = {
                        'success': True,
                        'message': f"Beneficiario '{nombre}' creado exitosamente",
                        'beneficiario_id': result['beneficiario_id'],
                        'folder_path': result.get('folder_path')
                    }
                    
                    # Agregar warning si existe
                    if 'warning' in result:
                        response_data['warning'] = result['warning']
                    
                    print(f"✅ Enviando respuesta JSON exitosa: {response_data}")
                    return jsonify(response_data)
                else:
                    print(f"⚠️  No es AJAX, redirigiendo...")
                    flash(f"Beneficiario '{nombre}' creado exitosamente con carpeta en Dropbox", "success")
                    print(f"Beneficiario creado: {result['message']} - Carpeta: {result.get('folder_path')}")
                    return redirect(url_for("users.crear_beneficiario"))
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    error_response = {
                        'success': False,
                        'error': result['error']
                    }
                    print(f"❌ Enviando respuesta de error: {error_response}")
                    return jsonify(error_response), 500
                else:
                    flash(f"Error al crear beneficiario: {result['error']}", "error")
                    print(f"Error creando beneficiario: {result['error']}")
                    return redirect(url_for("users.crear_beneficiario"))
            
        except Exception as e:
            # Manejar rollback de manera segura
            try:
                db.session.rollback()
            except Exception as rollback_error:
                print(f"Error en rollback: {rollback_error}")
            
            error_message = f'Error al crear beneficiario: {str(e)}'
            print(f"Error en crear_beneficiario: {e}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': error_message
                }), 500
            else:
                flash(error_message, "error")
                return redirect(url_for("users.crear_beneficiario"))
            
    return render_template("crear_beneficiario.html", titulares=titulares)





@bp.route("/listar_beneficiarios")
def listar_beneficiarios():
    titulares = User.query.filter_by(es_beneficiario=False).all()
    estructuras_titulares = {}
    estructuras_beneficiarios = {}

    dbx = get_dbx()
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
            # Si el campo 'activo' no viene en el formulario, por defecto dejar activo=True
            activo_value = request.form.get('activo')
            activo = True if activo_value is None else (activo_value == 'on')
            
            # Validaciones básicas
            if not email or not password:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"success": False, "error": "Email y contraseña son obligatorios"})
                flash('Email y contraseña son obligatorios', 'error')
                return redirect(url_for('users.listar_usuarios'))
            
            # Verificar si el usuario ya existe
            if User.query.filter_by(email=email).first():
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"success": False, "error": "El email ya está registrado"})
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
                rol=rol,
                activo=activo,
                fecha_registro=datetime.utcnow()
            )
            
            # Establecer contraseña
            user.set_password(password)
            
            # Procesar fecha de nacimiento
            if fecha_nacimiento_str:
                try:
                    fecha_nacimiento = datetime.strptime(fecha_nacimiento_str, '%Y-%m-%d').date()
                    user.fecha_nacimiento = fecha_nacimiento
                except ValueError:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({"success": False, "error": "Formato de fecha de nacimiento inválido"})
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
                
                # Agregar usuario a la BD primero para obtener el ID
                db.session.add(user)
                db.session.commit()
                
                # SINCRONIZACIÓN: Crear entrada de carpeta raíz en la BD
                from app.models import Folder
                carpeta_raiz = Folder(
                    name=email.split('@')[0],  # Usar parte del email como nombre
                    user_id=user.id,
                    dropbox_path=path,
                    es_publica=True
                )
                db.session.add(carpeta_raiz)
                print(f"INFO | Carpeta raíz creada en BD para usuario {user.id}: {path}")
                
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"success": False, "error": f"Error al crear carpeta en Dropbox: {str(e)}"})
                flash(f'Error al crear carpeta en Dropbox: {str(e)}', 'warning')
            
            # El usuario y carpeta raíz ya fueron agregados, hacer commit final
            db.session.commit()
            
            # Registrar la actividad de creación de usuario
            from app.utils.activity_logger import log_user_activity
            log_user_activity(
                user_id=user.id,
                accion='create_user',
                descripcion=f'Usuario creado con rol {rol}'
            )
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    "success": True, 
                    "message": f"Usuario {user.nombre_completo} creado exitosamente con rol {rol}",
                    "user_id": user.id
                })
            
            flash(f'Usuario {user.nombre_completo} creado exitosamente con rol {rol}', 'success')
            return redirect(url_for('users.listar_usuarios'))
            
        except Exception as e:
            db.session.rollback()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "error": f"Error al crear usuario: {str(e)}"})
            flash(f'Error al crear usuario: {str(e)}', 'error')
            return redirect(url_for('users.listar_usuarios'))
    
    # GET request - redirigir al listado (el modal se maneja en el frontend)
    return redirect(url_for('users.listar_usuarios'))

@bp.route('/listar_usuarios')
def listar_usuarios():
    """Vista para listar usuarios con paginación"""
    from app.utils.countries import get_countries_list, get_nationalities_list
    
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Mostrar 10 usuarios por página
    q = (request.args.get('q') or '').strip()
    
    # Obtener usuarios paginados (excluyendo clientes)
    query = User.query.filter(User.rol != 'cliente')
    if q:
        query = query.filter(
            or_(
                User.nombre.ilike(f'%{q}%'),
                User.apellido.ilike(f'%{q}%'),
                User.email.ilike(f'%{q}%')
            )
        )
    pagination = query.order_by(User.nombre).paginate(page=page, per_page=per_page, error_out=False)
    
    usuarios = pagination.items
    
    # Obtener listas de países y nacionalidades
    countries = get_countries_list()
    nationalities = get_nationalities_list()
    
    # Render completo si no es AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Devolver solo el tbody renderizado
        return render_template('usuarios/_users_table_body.html', usuarios=usuarios)

    return render_template('listar_usuarios.html', 
                         usuarios=usuarios, 
                         pagination=pagination,
                         countries=countries,
                         nationalities=nationalities,
                         q=q)

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
                'lector_extra_permissions': user.lector_extra_permissions,
                'alien_number': user.alien_number
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
        user.alien_number = request.form.get('alien_number')
        
        # Validar y actualizar rol
        nuevo_rol = request.form.get('rol')
        if nuevo_rol is not None and nuevo_rol.strip():  # Solo actualizar si se proporciona un valor válido
            user.rol = nuevo_rol
        else:
            # Si no se proporciona un rol válido, mantener el rol actual
            # o establecer un rol por defecto si no existe
            if not user.rol:
                user.rol = 'cliente'  # Rol por defecto
        
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
        
        # Procesar cambio de contraseña (si se proporciona)
        new_password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        if new_password or password_confirm:
            # Si se proporciona alguna contraseña, ambas son requeridas
            if not new_password or not password_confirm:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"success": False, "error": "Debe completar ambos campos de contraseña"})
                flash('Debe completar ambos campos de contraseña', 'error')
                return redirect(url_for('users.listar_usuarios'))
            
            # Validar que las contraseñas coincidan
            if new_password != password_confirm:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"success": False, "error": "Las contraseñas no coinciden"})
                flash('Las contraseñas no coinciden', 'error')
                return redirect(url_for('users.listar_usuarios'))
            
            # Validar longitud mínima
            if len(new_password) < 6:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"success": False, "error": "La contraseña debe tener al menos 6 caracteres"})
                flash('La contraseña debe tener al menos 6 caracteres', 'error')
                return redirect(url_for('users.listar_usuarios'))
            
            # Actualizar contraseña
            user.set_password(new_password)
            
            # Registrar actividad de cambio de contraseña
            from app.utils.activity_logger import log_user_activity
            log_user_activity(
                user_id=user.id,
                accion='change_password',
                descripcion=f'Contraseña cambiada por administrador {current_user.email}'
            )
        
        # Procesar fecha de nacimiento
        fecha_nacimiento_str = request.form.get('fecha_nacimiento')
        if fecha_nacimiento_str:
            try:
                fecha_nacimiento = datetime.strptime(fecha_nacimiento_str, '%Y-%m-%d').date()
                user.fecha_nacimiento = fecha_nacimiento
            except ValueError:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"success": False, "error": "Formato de fecha de nacimiento inválido"})
                flash('Formato de fecha de nacimiento inválido', 'error')
                return redirect(url_for('users.listar_usuarios'))
        
        # Verificar email único
        existing_user = User.query.filter(User.email == user.email, User.id != user.id).first()
        if existing_user:
            flash('El email ya está registrado por otro usuario', 'error')
            return redirect(url_for('users.listar_usuarios'))
        
        db.session.commit()
        
        # Registrar la actividad de actualización
        from app.utils.activity_logger import log_profile_update
        fields_updated = ['email', 'nombre', 'apellido', 'telefono', 'ciudad', 'estado', 'direccion', 'codigo_postal', 'nacionality', 'country', 'rol', 'activo', 'fecha_nacimiento']
        if new_password:
            fields_updated.append('password')
        
        log_profile_update(
            user_id=user.id,
            fields_updated=fields_updated
        )
        
        # Mensaje de éxito personalizado
        success_message = f'Usuario {user.nombre or user.email} actualizado exitosamente'
        if new_password:
            success_message += ' (incluye cambio de contraseña)'
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": True, "message": success_message})
        
        flash(success_message, 'success')
        
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

@bp.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    """Eliminar un usuario administrativo"""
    try:
        # Verificar permisos de administrador
        if not current_user.puede_administrar():
            return jsonify({'success': False, 'error': 'No tienes permisos para realizar esta acción.'}), 403
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'Usuario no encontrado.'}), 404
        
        # No permitir eliminar al usuario actual
        if user.id == current_user.id:
            return jsonify({'success': False, 'error': 'No puedes eliminar tu propia cuenta.'}), 400
        
        # No permitir eliminar superadmins (excepto por otros superadmins)
        if user.rol == 'superadmin' and current_user.rol != 'superadmin':
            return jsonify({'success': False, 'error': 'No puedes eliminar un Super Admin.'}), 403
        
        # Verificar si el usuario tiene contenido asociado (solo para información)
        archivos_count = Archivo.query.filter_by(usuario_id=user_id).count()
        carpetas_count = Folder.query.filter_by(user_id=user_id).count()
        
        # Eliminar archivos y carpetas asociadas
        if archivos_count > 0:
            Archivo.query.filter_by(usuario_id=user_id).delete()
        
        if carpetas_count > 0:
            Folder.query.filter_by(user_id=user_id).delete()
        
        # Eliminar beneficiarios asociados al usuario
        beneficiarios_count = Beneficiario.query.filter_by(titular_id=user_id).count()
        if beneficiarios_count > 0:
            Beneficiario.query.filter_by(titular_id=user_id).delete()
        
        # Eliminar actividades del usuario
        UserActivityLog.query.filter_by(user_id=user_id).delete()
        
        # Eliminar el usuario
        db.session.delete(user)
        
        # Registrar actividad
        actividad = UserActivityLog(
            user_id=current_user.id,
            accion="eliminar_usuario",
            descripcion=f"Eliminó usuario administrativo {user.email}"
        )
        db.session.add(actividad)
        
        db.session.commit()
        
        # Crear mensaje detallado
        mensaje = f'Usuario "{user.email}" eliminado exitosamente.'
        if archivos_count > 0 or carpetas_count > 0 or beneficiarios_count > 0:
            detalles = []
            if archivos_count > 0:
                detalles.append(f"{archivos_count} archivo(s)")
            if carpetas_count > 0:
                detalles.append(f"{carpetas_count} carpeta(s)")
            if beneficiarios_count > 0:
                detalles.append(f"{beneficiarios_count} beneficiario(s)")
            
            mensaje += f" También se eliminaron: {', '.join(detalles)}."
        
        return jsonify({
            'success': True, 
            'message': mensaje
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error al eliminar usuario: {str(e)}'}), 500
