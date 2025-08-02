# routes/usuarios.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import User, Folder, Archivo, UserActivityLog
from app import db
from sqlalchemy import or_
import dropbox
from datetime import datetime

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

@bp.route('/usuarios/<int:usuario_id>/carpetas-json')
@login_required
def obtener_carpetas_usuario_json(usuario_id):
    """Obtener carpetas de un usuario en formato JSON"""
    if not current_user.puede_administrar():
        return jsonify({"error": "No tienes permisos"}), 403
    
    usuario = User.query.get_or_404(usuario_id)
    carpetas = Folder.query.filter_by(user_id=usuario_id).all()
    
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
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        
        # Leer archivo
        archivo_content = archivo.read()
        
        # Subir a Dropbox
        dropbox_path = f"{carpeta.dropbox_path}/{archivo.filename}"
        dbx.files_upload(archivo_content, dropbox_path, mode=dropbox.files.WriteMode("overwrite"))
        
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
    activo = request.form.get('activo') == 'on'
    
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

@bp.route('/usuarios/<int:usuario_id>/eliminar', methods=['POST'])
@login_required
def eliminar_usuario(usuario_id):
    """Eliminar un usuario y todas sus carpetas/archivos de Dropbox"""
    if not current_user.puede_administrar():
        flash("No tienes permisos para realizar esta acción.", "error")
        return redirect(url_for('usuarios.lista_usuarios'))
    
    usuario = User.query.get_or_404(usuario_id)
    
    # No permitir eliminar al usuario actual
    if usuario.id == current_user.id:
        flash("No puedes eliminar tu propia cuenta.", "error")
        return redirect(url_for('usuarios.lista_usuarios'))
    
    try:
        # Conectar a Dropbox
        from flask import current_app
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        
        # Eliminar carpetas y archivos de Dropbox
        if usuario.dropbox_folder_path:
            try:
                # Listar todo el contenido de la carpeta del usuario
                res = dbx.files_list_folder(usuario.dropbox_folder_path, recursive=True)
                
                # Eliminar archivos primero
                for entry in res.entries:
                    if hasattr(entry, 'path_display'):
                        try:
                            dbx.files_delete_v2(entry.path_display)
                        except dropbox.exceptions.ApiError as e:
                            if "not_found" not in str(e):
                                print(f"Error eliminando {entry.path_display}: {e}")
                
                # Eliminar la carpeta raíz del usuario
                dbx.files_delete_v2(usuario.dropbox_folder_path)
                
            except dropbox.exceptions.ApiError as e:
                if "not_found" not in str(e):
                    print(f"Error eliminando carpeta de usuario: {e}")
        
        # Eliminar registros de la base de datos
        # Eliminar archivos
        Archivo.query.filter_by(usuario_id=usuario_id).delete()
        
        # Eliminar carpetas
        Folder.query.filter_by(user_id=usuario_id).delete()
        
        # Eliminar actividades del usuario
        UserActivityLog.query.filter_by(user_id=usuario_id).delete()
        
        # Eliminar el usuario
        db.session.delete(usuario)
        
        # Registrar actividad
        actividad = UserActivityLog(
            user_id=current_user.id,
            accion="eliminar_usuario",
            descripcion=f"Eliminó usuario {usuario.email} y todo su contenido"
        )
        db.session.add(actividad)
        
        db.session.commit()
        
        flash(f"Usuario '{usuario.email}' eliminado exitosamente junto con todas sus carpetas y archivos.", "success")
        return redirect(url_for('usuarios.lista_usuarios'))
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error al eliminar usuario: {str(e)}", "error")
        return redirect(url_for('usuarios.lista_usuarios'))
