from app.dropbox_utils import get_dbx, with_base_folder
# routes/usuarios.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import User, Folder, Archivo, UserActivityLog, Beneficiario, FolderPermiso
from app import db
from sqlalchemy import or_
import dropbox
from datetime import datetime
from dropbox.exceptions import ApiError
from sqlalchemy.exc import IntegrityError

bp = Blueprint('usuarios', __name__)

@bp.route('/usuarios')
@login_required
def lista_usuarios():
    # Verificar permisos de administrador
    if not current_user.puede_administrar():
        flash("No tienes permisos para acceder a esta sección.", "error")
        return redirect(url_for('main.profile'))
    
    # Parámetros de búsqueda y paginación
    rol = request.args.get('rol', 'cliente')  # 'cliente' por default
    q = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))

    # Query base filtrando por rol
    query = User.query.filter(User.rol == rol)

    # Si hay búsqueda, filtra por nombre/email/rol
    if q:
        query = query.filter(or_(
            User.nombre.ilike(f"%{q}%"),
            User.email.ilike(f"%{q}%"),
            User.rol.ilike(f"%{q}%"),
        ))

    # Paginación
    pagination = query.order_by(User.nombre).paginate(page=page, per_page=per_page, error_out=False)
    usuarios = pagination.items

    # Carpetas por usuario (solo cuenta, para el badge)
    carpetas_por_usuario = {
        u.id: Folder.query.filter_by(user_id=u.id).count() for u in usuarios
    }

    # Para AJAX (búsqueda en vivo) devolver solo el tbody renderizado
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render_template(
            "usuarios/_usuarios_tbody.html",
            usuarios=usuarios,
            carpetas_por_usuario=carpetas_por_usuario,
        )

    return render_template(
        "lista_usuarios.html",
        usuarios=usuarios,
        carpetas_por_usuario=carpetas_por_usuario,
        pagination=pagination,
        rol=rol,
        q=q,
    )

@bp.route('/usuarios/<int:usuario_id>/historial')
@login_required
def ver_historial_usuario(usuario_id):
    """Ver historial de actividades de un usuario"""
    if not current_user.puede_administrar():
        flash("No tienes permisos para acceder a esta sección.", "error")
        return redirect(url_for('main.profile'))
    
    usuario = User.query.get_or_404(usuario_id)
    
    # Obtener actividades del usuario
    actividades = UserActivityLog.query.filter_by(user_id=usuario_id)\
        .order_by(UserActivityLog.fecha.desc())\
        .limit(50)\
        .all()
    
    # Obtener archivos del usuario
    archivos = Archivo.query.filter_by(usuario_id=usuario_id)\
        .order_by(Archivo.fecha_subida.desc())\
        .limit(20)\
        .all()
    
    # Obtener carpetas del usuario
    carpetas = Folder.query.filter_by(user_id=usuario_id)\
        .order_by(Folder.fecha_creacion.desc())\
        .all()
    
    # Si es una petición AJAX, devolver solo el contenido
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render_template(
            "usuarios/historial_usuario.html",
            usuario=usuario,
            actividades=actividades,
            archivos=archivos,
            carpetas=carpetas
        )
    
    return render_template(
        "usuarios/historial_usuario.html",
        usuario=usuario,
        actividades=actividades,
        archivos=archivos,
        carpetas=carpetas
    )

@bp.route('/usuarios/<int:usuario_id>/historial-json')
@login_required
def obtener_historial_usuario_json(usuario_id):
    """Obtener historial de un usuario en formato JSON"""
    if not current_user.puede_administrar():
        return jsonify({"error": "No tienes permisos"}), 403
    
    usuario = User.query.get_or_404(usuario_id)
    
    # Obtener actividades del usuario
    actividades = UserActivityLog.query.filter_by(user_id=usuario_id)\
        .order_by(UserActivityLog.fecha.desc())\
        .limit(50)\
        .all()
    
    # Obtener archivos del usuario
    archivos = Archivo.query.filter_by(usuario_id=usuario_id)\
        .order_by(Archivo.fecha_subida.desc())\
        .limit(20)\
        .all()
    
    # Obtener carpetas del usuario
    carpetas = Folder.query.filter_by(user_id=usuario_id)\
        .order_by(Folder.fecha_creacion.desc())\
        .all()
    
    # Convertir a formato JSON
    actividades_data = []
    for actividad in actividades:
        actividades_data.append({
            'id': actividad.id,
            'accion': actividad.accion,
            'descripcion': actividad.descripcion,
            'fecha': actividad.fecha.isoformat() if actividad.fecha else None,
            'ip_address': actividad.ip_address,
            'user_agent': actividad.user_agent
        })
    
    archivos_data = []
    for archivo in archivos:
        archivos_data.append({
            'id': archivo.id,
            'nombre': archivo.nombre,
            'categoria': archivo.categoria,
            'subcategoria': archivo.subcategoria,
            'dropbox_path': archivo.dropbox_path,
            'fecha_subida': archivo.fecha_subida.isoformat() if archivo.fecha_subida else None,
            'tamano': archivo.tamano,
            'extension': archivo.extension,
            'descripcion': archivo.descripcion
        })
    
    carpetas_data = []
    for carpeta in carpetas:
        carpetas_data.append({
            'id': carpeta.id,
            'name': carpeta.name,
            'dropbox_path': carpeta.dropbox_path,
            'es_publica': carpeta.es_publica,
            'fecha_creacion': carpeta.fecha_creacion.isoformat() if carpeta.fecha_creacion else None
        })
    
    return jsonify({
        'usuario': {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'apellido': usuario.apellido,
            'email': usuario.email,
            'rol': usuario.rol,
            'activo': usuario.activo,
            'fecha_registro': usuario.fecha_registro.isoformat() if usuario.fecha_registro else None,
            'ultimo_acceso': usuario.ultimo_acceso.isoformat() if usuario.ultimo_acceso else None
        },
        'actividades': actividades_data,
        'archivos': archivos_data,
        'carpetas': carpetas_data,
        'estadisticas': {
            'total_actividades': len(actividades_data),
            'total_archivos': len(archivos_data),
            'total_carpetas': len(carpetas_data)
        }
    })

@bp.route('/api/lectores/<int:usuario_id>/historial')
@login_required
def api_historial_para_lectores(usuario_id):
    """API para que usuarios con rol 'lector' puedan ver historial de clientes.

    Reglas:
    - Solo lectores y administradores/superadmins pueden consultar este endpoint.
    - Si el solicitante es lector, solo se permite consultar usuarios con rol 'cliente'.
    """
    # Verificar rol del solicitante
    solicitante_es_admin = hasattr(current_user, 'puede_administrar') and current_user.puede_administrar()
    if not (solicitante_es_admin or (hasattr(current_user, 'rol') and current_user.rol == 'lector')):
        return jsonify({'error': 'Acceso denegado'}), 403

    usuario = User.query.get_or_404(usuario_id)

    # Si es lector, solo puede ver historial de clientes
    if current_user.rol == 'lector' and usuario.rol != 'cliente':
        return jsonify({'error': 'Solo puedes ver historial de clientes'}), 403

    # Actividades (limitadas)
    actividades = UserActivityLog.query.filter_by(user_id=usuario_id) \
        .order_by(UserActivityLog.fecha.desc()) \
        .limit(50) \
        .all()

    # Mapeo de acciones a etiquetas en español
    accion_labels = {
        'login': 'Inicio de sesión',
        'logout': 'Cierre de sesión',
        'profile_view': 'Vista de perfil',
        'profile_update': 'Actualización de perfil',
        'user_registered': 'Usuario registrado',
        'registration_completed': 'Registro completado',
        'password_changed': 'Cambio de contraseña',
        'password_reset': 'Restablecimiento de contraseña',
        'dashboard_access': 'Acceso al panel',
        'dashboard_admin_access': 'Acceso al panel de administrador',
        'admin_dashboard_access': 'Acceso al panel administrativo',
        'dashboard_cliente_access': 'Acceso al panel de cliente',
        'dashboard_lector_access': 'Acceso al panel de lector',
        'file_uploaded': 'Archivo subido',
        'file_moved': 'Archivo movido',
        'file_renamed': 'Archivo renombrado',
        'file_hidden': 'Archivo ocultado',
        'folder_created': 'Carpeta creada',
        'folder_deleted': 'Carpeta eliminada',
        'folder_hidden': 'Carpeta ocultada',
        'folder_renamed': 'Carpeta renombrada',
        'advanced_search': 'Búsqueda avanzada',
        'bulk_export': 'Exportación masiva',
        'beneficiary_update': 'Actualización de beneficiario',
        'importar_archivo': 'Importación de archivo',
        'editar_usuario': 'Edición de usuario'
    }

    actividades_data = []
    for actividad in actividades:
        codigo = actividad.accion or ''
        actividades_data.append({
            'id': actividad.id,
            'accion': accion_labels.get(codigo, codigo or 'Actividad'),
            'accion_code': codigo,
            'descripcion': actividad.descripcion,
            'fecha': actividad.fecha.isoformat() if actividad.fecha else None,
        })

    # Archivos recientes del cliente (resumen)
    archivos = Archivo.query.filter_by(usuario_id=usuario_id) \
        .order_by(Archivo.fecha_subida.desc()) \
        .limit(20) \
        .all()

    archivos_data = []
    for archivo in archivos:
        archivos_data.append({
            'id': archivo.id,
            'nombre': archivo.nombre,
            'fecha_subida': archivo.fecha_subida.isoformat() if archivo.fecha_subida else None,
            'extension': getattr(archivo, 'extension', None),
            'estado': getattr(archivo, 'estado', None)
        })

    # Resumen de carpetas (no se exponen datos sensibles)
    carpetas = Folder.query.filter_by(user_id=usuario_id).order_by(Folder.fecha_creacion.desc()).all()
    carpetas_data = []
    for carpeta in carpetas:
        carpetas_data.append({
            'id': carpeta.id,
            'name': carpeta.name,
            'es_publica': carpeta.es_publica,
            'fecha_creacion': carpeta.fecha_creacion.isoformat() if carpeta.fecha_creacion else None
        })

    return jsonify({
        'success': True,
        'usuario': {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'apellido': usuario.apellido,
            'email': usuario.email,
            'rol': usuario.rol
        },
        'actividades': actividades_data,
        'archivos': archivos_data,
        'carpetas': carpetas_data
    })

@bp.route('/usuarios/<int:usuario_id>/carpetas-json')
@login_required
def obtener_carpetas_usuario_json(usuario_id):
    """Obtener carpetas de un usuario en formato JSON"""
    if not current_user.puede_administrar():
        return jsonify({"error": "No tienes permisos"}), 403
    
    usuario = User.query.get_or_404(usuario_id)
    
    # Aplicar filtro de carpetas según el rol del usuario actual
    if current_user.rol == "cliente":
        # Cliente solo ve carpetas públicas
        carpetas = Folder.query.filter_by(user_id=usuario_id, es_publica=True).all()
    elif current_user.rol == "lector":
        # Lector ve todas las carpetas
        carpetas = Folder.query.filter_by(user_id=usuario_id).all()
    elif current_user.rol == "admin" or current_user.rol == "superadmin":
        # Admin ve todas las carpetas
        carpetas = Folder.query.filter_by(user_id=usuario_id).all()
    else:
        # Otros roles solo ven carpetas públicas
        carpetas = Folder.query.filter_by(user_id=usuario_id, es_publica=True).all()
    
    carpetas_data = []
    for carpeta in carpetas:
        carpetas_data.append({
            'id': carpeta.id,
            'name': carpeta.name,
            'dropbox_path': carpeta.dropbox_path,
            'es_publica': carpeta.es_publica,
            'fecha_creacion': carpeta.fecha_creacion.isoformat() if carpeta.fecha_creacion else None
        })
    
    return jsonify({
        'usuario': {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'email': usuario.email
        },
        'carpetas': carpetas_data
    })

@bp.route('/usuarios/<int:usuario_id>/datos-json')
@login_required
def obtener_datos_usuario_json(usuario_id):
    """Obtener datos de un usuario en formato JSON"""
    if not current_user.puede_administrar():
        return jsonify({"error": "No tienes permisos"}), 403
    
    usuario = User.query.get_or_404(usuario_id)
    
    return jsonify({
        'id': usuario.id,
        'nombre': usuario.nombre,
        'apellido': usuario.apellido,
        'email': usuario.email,
        'telefono': usuario.telefono,
        'alien_number': usuario.alien_number,
        'direccion': usuario.direccion,
        'ciudad': usuario.ciudad,
        'estado': usuario.estado,
        'codigo_postal': usuario.codigo_postal,
        'rol': usuario.rol,
        'activo': usuario.activo,
        'fecha_registro': usuario.fecha_registro.isoformat() if usuario.fecha_registro else None,
        'ultimo_acceso': usuario.ultimo_acceso.isoformat() if usuario.ultimo_acceso else None
    })

@bp.route('/usuarios/<int:usuario_id>/importar-archivo', methods=['GET', 'POST'])
@login_required
def importar_archivo_usuario(usuario_id):
    """Importar archivo para un usuario específico"""
    if not current_user.puede_administrar():
        flash("No tienes permisos para acceder a esta sección.", "error")
        return redirect(url_for('main.profile'))
    
    usuario = User.query.get_or_404(usuario_id)
    
    if request.method == 'GET':
        # Obtener carpetas del usuario para mostrar opciones
        carpetas = Folder.query.filter_by(user_id=usuario_id).all()
        return render_template(
            "usuarios/importar_archivo.html",
            usuario=usuario,
            carpetas=carpetas
        )
    
    # POST: procesar subida de archivo
    archivo = request.files.get('archivo')
    carpeta_destino = request.form.get('carpeta_destino')
    descripcion = request.form.get('descripcion', '')
    
    if not archivo or not carpeta_destino:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "error": "Debes seleccionar un archivo y una carpeta de destino."})
        flash("Debes seleccionar un archivo y una carpeta de destino.", "error")
        return redirect(url_for('usuarios.importar_archivo_usuario', usuario_id=usuario_id))
    
    try:
        # Verificar que la carpeta existe y pertenece al usuario
        carpeta = Folder.query.filter_by(id=carpeta_destino, user_id=usuario_id).first()
        if not carpeta:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "error": "Carpeta de destino no válida."})
            flash("Carpeta de destino no válida.", "error")
            return redirect(url_for('usuarios.importar_archivo_usuario', usuario_id=usuario_id))
        
        # Conectar a Dropbox
        from flask import current_app
        dbx = get_dbx()
        
        # Leer archivo
        archivo_content = archivo.read()
        
        # Subir a Dropbox
        dropbox_path = f"{carpeta.dropbox_path}/{archivo.filename}"
        dbx.files_upload(archivo_content, with_base_folder(dropbox_path), mode=dropbox.files.WriteMode("overwrite"))
        
        # Guardar en base de datos
        nuevo_archivo = Archivo(
            nombre=archivo.filename,
            categoria=carpeta.name,
            subcategoria="Importado",
            dropbox_path=dropbox_path,
            usuario_id=usuario_id,
            descripcion=descripcion
        )
        db.session.add(nuevo_archivo)
        
        # Registrar actividad
        actividad = UserActivityLog(
            user_id=current_user.id,
            accion="importar_archivo",
            descripcion=f"Importó archivo '{archivo.filename}' para usuario {usuario.email}"
        )
        db.session.add(actividad)
        
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": True, "message": f"Archivo '{archivo.filename}' importado exitosamente."})
        
        flash(f"Archivo '{archivo.filename}' importado exitosamente.", "success")
        return redirect(url_for('usuarios.ver_historial_usuario', usuario_id=usuario_id))
        
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "error": f"Error al importar archivo: {str(e)}"})
        flash(f"Error al importar archivo: {str(e)}", "error")
        return redirect(url_for('usuarios.importar_archivo_usuario', usuario_id=usuario_id))

@bp.route('/usuarios/<int:usuario_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_usuario(usuario_id):
    """Editar información de un usuario"""
    if not current_user.puede_administrar():
        flash("No tienes permisos para acceder a esta sección.", "error")
        return redirect(url_for('main.profile'))
    
    usuario = User.query.get_or_404(usuario_id)
    
    if request.method == 'GET':
        return render_template(
            "usuarios/editar_usuario.html",
            usuario=usuario
        )
    
    # POST: procesar edición
    nombre = request.form.get('nombre')
    apellido = request.form.get('apellido')
    email = request.form.get('email')
    telefono = request.form.get('telefono')
    ciudad = request.form.get('ciudad')
    estado = request.form.get('estado')
    direccion = request.form.get('direccion')
    codigo_postal = request.form.get('codigo_postal')
    rol = request.form.get('rol')
    alien_number = request.form.get('alien_number')
    # Por defecto, si no llega el campo 'activo', dejar al usuario ACTIVO
    activo_value = request.form.get('activo')
    activo = True if activo_value is None else (activo_value == 'on')
    
    # Validar email único
    if email != usuario.email:
        usuario_existente = User.query.filter_by(email=email).first()
        if usuario_existente:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "error": "El email ya está en uso por otro usuario."})
            flash("El email ya está en uso por otro usuario.", "error")
            return redirect(url_for('usuarios.editar_usuario', usuario_id=usuario_id))
    
    try:
        # Actualizar datos del usuario
        usuario.nombre = nombre
        usuario.apellido = apellido
        usuario.email = email
        usuario.telefono = telefono
        usuario.ciudad = ciudad
        usuario.estado = estado
        usuario.direccion = direccion
        usuario.codigo_postal = codigo_postal
        usuario.rol = rol
        usuario.activo = activo
        usuario.alien_number = alien_number
        
        # Registrar actividad
        actividad = UserActivityLog(
            user_id=current_user.id,
            accion="editar_usuario",
            descripcion=f"Editó información del usuario {usuario.email}"
        )
        db.session.add(actividad)
        
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": True, "message": "Usuario actualizado exitosamente."})
        
        flash("Usuario actualizado exitosamente.", "success")
        return redirect(url_for('usuarios.lista_usuarios'))
        
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "error": f"Error al actualizar usuario: {str(e)}"})
        flash(f"Error al actualizar usuario: {str(e)}", "error")
        return redirect(url_for('usuarios.editar_usuario', usuario_id=usuario_id))

def _safe_delete_dropbox_folder(dbx, path):
    if not path:
        return
    full_path = with_base_folder(path)
    try:
        dbx.files_delete_v2(full_path)
    except ApiError as e:
        err = str(e)
        if "path_lookup/not_found" in err or "not_found" in err:
            return
        raise
    
@bp.route('/usuarios/<int:usuario_id>/eliminar', methods=['POST'])
@login_required
def eliminar_usuario(usuario_id):
    if not current_user.puede_administrar():
        return jsonify({"success": False, "error": "No tienes permisos"}), 403

    usuario = User.query.get_or_404(usuario_id)

    if usuario.id == current_user.id:
        return jsonify({"success": False, "error": "No puedes eliminar tu propia cuenta."}), 400

    try:
        dbx = get_dbx()
        if dbx is None:
            return jsonify({'success': False, 'error': 'No se pudo conectar a Dropbox (token inválido o no configurado)'}), 500
        dropbox_path = getattr(usuario, 'dropbox_folder_path', None)
        if dropbox_path:
            try:
                full_path = with_base_folder(dropbox_path)
                dbx.files_delete_v2(full_path)
            except ApiError as e:
                # Ignorar error not_found (la carpeta ya no existe o nunca existió)
                if (
                    hasattr(e, "error") 
                    and hasattr(e.error, "is_path_lookup") 
                    and e.error.is_path_lookup()
                    and hasattr(e.error.get_path_lookup(), "is_not_found")
                    and e.error.get_path_lookup().is_not_found()
                ):
                    pass  # continuar con la eliminación, no es crítico
                else:
                    return jsonify({"success": False, "step": "dropbox_delete", "error": str(e)}), 500
        carpeta_ids = [c.id for c in Folder.query.with_entities(Folder.id).filter_by(user_id=usuario_id).all()]
        try:
            if carpeta_ids:
                FolderPermiso.query.filter(FolderPermiso.folder_id.in_(carpeta_ids)).delete(synchronize_session=False)
            Archivo.query.filter_by(usuario_id=usuario_id).delete(synchronize_session=False)
            Folder.query.filter_by(user_id=usuario_id).delete(synchronize_session=False)
            Beneficiario.query.filter_by(titular_id=usuario_id).delete(synchronize_session=False)
            UserActivityLog.query.filter_by(user_id=usuario_id).delete(synchronize_session=False)
            # Eliminar notificaciones del usuario para evitar errores de clave externa NOT NULL
            from app.models import Notification
            Notification.query.filter_by(user_id=usuario_id).delete(synchronize_session=False)
            db.session.delete(usuario)
            actividad = UserActivityLog(
                user_id=current_user.id,
                accion="eliminar_usuario",
                descripcion=f"Eliminó usuario {usuario.email} y todo su contenido (PRODUCCION)"
            )
            db.session.add(actividad)
            db.session.commit()
        except IntegrityError as ie:
            db.session.rollback()
            return jsonify({"success": False, "step": "db_commit", "error": str(ie.orig if getattr(ie, 'orig', None) else ie)}), 500
        except Exception as db_e:
            db.session.rollback()
            return jsonify({"success": False, "step": "db_other", "error": str(db_e)}), 500
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True}), 200
        flash('Usuario y toda su información eliminados correctamente.', 'success')
        return redirect(url_for('usuarios.lista_usuarios'))
    except Exception as e:
        return jsonify({"success": False, "step": "unexpected", "error": str(e)}), 500