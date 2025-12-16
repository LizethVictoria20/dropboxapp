from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash

from app import db
from app.models import User, Folder, Archivo, UserActivityLog, Notification, Beneficiario, SystemSettings
from forms import ProfileForm
from app.routes.auth import role_required
from app.utils.dashboard_stats import (
    get_dashboard_stats, get_charts_data, get_file_types_stats, 
    get_recent_files_with_users, get_recent_activity
)
from app.utils.notification_utils import (
    obtener_notificaciones_no_leidas, contar_notificaciones_no_leidas,
    marcar_notificacion_leida, marcar_todas_notificaciones_leidas
)

bp = Blueprint('main', __name__)


@bp.route('/', methods=['GET', 'POST'])
def auth_direct():
    """Ruta directa para /auth que muestra el login sin redirección"""
    from app.routes.auth import login
    return login()

@bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard principal - redirige según el rol"""
    
    # Verificar que el usuario esté autenticado antes de acceder a sus atributos
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
        return redirect(url_for("auth.login"))
    
    # Registrar actividad de acceso al dashboard
    current_user.registrar_actividad('dashboard_access', 'Acceso al dashboard principal')
    
    # Redirigir según el rol
    if current_user.rol == 'cliente':
        return redirect(url_for('listar_dropbox.subir_archivo'))
    else:
        # Admin, superadmin y lector van al dashboard admin
        return redirect(url_for('main.dashboard_admin'))

@bp.route('/dashboard/cliente')
@login_required
@role_required('cliente')
def dashboard_cliente():
    """Dashboard específico para clientes"""
    
    # Registrar actividad de acceso al dashboard de cliente
    current_user.registrar_actividad('dashboard_cliente_access', 'Acceso al dashboard de cliente')
    
    # Obtener estadísticas del cliente
    total_archivos = Archivo.query.filter_by(usuario_id=current_user.id).count()
    total_carpetas = Folder.query.filter_by(user_id=current_user.id, es_publica=True).count()
    beneficiarios = Beneficiario.query.filter_by(titular_id=current_user.id).count()
    
    # Crear diccionario de estadísticas
    stats = {
        'total_archivos': total_archivos,
        'mis_carpetas': total_carpetas,
        'beneficiarios': beneficiarios
    }
    
    # Actividad reciente (últimas 5 actividades)
    actividades_recientes = UserActivityLog.query.filter_by(user_id=current_user.id)\
                                                .order_by(desc(UserActivityLog.fecha))\
                                                .limit(5).all()
    
    # Carpetas recientes del usuario (últimas 5) - solo públicas para clientes
    carpetas_recientes = Folder.query.filter_by(user_id=current_user.id, es_publica=True)\
        .order_by(Folder.fecha_creacion.desc())\
        .limit(5).all()
    
    # Notificaciones no leídas del usuario
    notificaciones = Notification.query.filter_by(user_id=current_user.id, leida=False)\
        .order_by(Notification.fecha_creacion.desc())\
        .limit(5).all()
    
    # Registrar actividad de acceso al dashboard
    current_user.registrar_actividad('dashboard_access', 'Acceso al dashboard de cliente')
    
    return render_template('dashboard/cliente.html',
                         stats=stats,
                         actividades_recientes=actividades_recientes,
                         carpetas_recientes=carpetas_recientes,
                         notificaciones=notificaciones)

@bp.route('/test-charts')
def test_charts():
    """Página de prueba simple para Chart.js (sin login)"""
    return render_template('test_simple.html')

@bp.route('/dashboard/working')
@login_required
@role_required('admin')
def dashboard_working():
    """Dashboard funcional que usa el mismo método que test-charts"""
    from app.utils.dashboard_stats import (
        get_dashboard_stats, get_charts_data, get_file_types_stats, 
        get_recent_files_with_users
    )
    
    # Obtener todas las estadísticas
    stats = get_dashboard_stats('month')
    charts_data = get_charts_data()
    file_types_general = get_file_types_stats()
    recent_files = get_recent_files_with_users(10)
    
    return render_template('dashboard/admin_working.html',
                         stats=stats,
                         charts_data=charts_data,
                         file_types_general=file_types_general,
                         recent_files=recent_files)

@bp.route('/dashboard/test')
@login_required
@role_required('admin')
def dashboard_test():
    """Dashboard de prueba para verificar Chart.js"""
    from app.utils.dashboard_stats import get_dashboard_stats
    
    # Obtener estadísticas básicas
    stats = get_dashboard_stats('month')
    
    return render_template('dashboard/admin_simple.html', stats=stats)

@bp.route('/dashboard/admin')
@login_required
def dashboard_admin():
    """Dashboard específico para administradores y lectores"""
    
    # Verificar que el usuario tenga permisos de admin o sea lector
    if not (current_user.puede_administrar() or current_user.es_lector()):
        flash('No tienes permisos para acceder a esta página.', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Registrar actividad de acceso al dashboard de admin
    current_user.registrar_actividad('dashboard_admin_access', 'Acceso al dashboard de administrador')
    
    # Estadísticas del sistema
    stats = {
        'total_usuarios': User.query.count(),
        'total_archivos': Archivo.query.count(),
        'total_carpetas': Folder.query.count(),
        'usuarios_activos': User.query.filter_by(activo=True).count(),
        'usuarios_inactivos': User.query.filter_by(activo=False).count(),
        'clientes': User.query.filter_by(rol='cliente').count(),
        'admins': User.query.filter_by(rol='admin').count(),
        'superadmins': User.query.filter_by(rol='superadmin').count(),
        'lectores': User.query.filter_by(rol='lector').count()
    }
    
    # Obtener el período seleccionado (por defecto 'month') y si se debe mostrar todo el historial
    period = request.args.get('period', 'month')
    show_all = request.args.get('show_all', '0') in ['1', 'true', 'True']
    selected_period = period
    
    # Generar todas las estadísticas
    stats = get_dashboard_stats(period)
    charts_data = get_charts_data()
    
    # Tipos de archivo - general (todos los tiempos)
    file_types_general = get_file_types_stats()
    
    # Tipos de archivo - para el período seleccionado
    from app.utils.dashboard_stats import calculate_period_dates
    start_date, end_date = calculate_period_dates(period)
    file_types_recent_initial = get_file_types_stats(start_date, end_date)
    
    # Archivos recientes con usuarios (soportar mostrar todo)
    recent_files = get_recent_files_with_users(None if show_all else 10)
    
    # Actividad reciente del sistema
    recent_activity = get_recent_activity(15)
    
    # Distribución real de usuarios por rol
    usuarios_por_rol = db.session.query(
        User.rol, 
        db.func.count(User.id).label('cantidad')
    ).group_by(User.rol).all()
    
    distribucion_roles = {
        'superadmin': 0,
        'admin': 0,
        'cliente': 0,
        'lector': 0
    }
    
    for rol, cantidad in usuarios_por_rol:
        if rol in distribucion_roles:
            distribucion_roles[rol] = cantidad
    
    # Usuarios más activos
    usuarios_activos_raw = db.session.query(
        User.id,
        User.nombre,
        User.apellido,
        User.email,
        db.func.count(UserActivityLog.id).label('actividades')
    ).join(UserActivityLog)\
     .group_by(User.id, User.nombre, User.apellido, User.email)\
     .order_by(db.desc('actividades'))\
     .limit(5).all()
    
    usuarios_activos = []
    for resultado in usuarios_activos_raw:
        usuario_data = {
            'nombre_completo': f"{resultado.nombre} {resultado.apellido}" if resultado.nombre and resultado.apellido else resultado.email.split('@')[0],
            'email': resultado.email,
            'actividades': resultado.actividades
        }
        usuarios_activos.append(type('obj', (object,), usuario_data)())
    
    # Registrar actividad de acceso al dashboard admin
    current_user.registrar_actividad('admin_dashboard_access', 'Acceso al dashboard administrativo')
    
    # Si es una petición AJAX, devolver solo los datos que necesita JavaScript
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'stats': stats,
            'file_types_recent': file_types_recent_initial,
            'charts_data': charts_data
        })
    
    # Para peticiones normales, renderizar el template completo
    return render_template('dashboard/admin.html',
                         stats=stats,
                         charts_data=charts_data,
                         file_types_general=file_types_general,
                         file_types_recent_initial=file_types_recent_initial,
                         recent_files=recent_files,
                         recent_activity=recent_activity,
                         distribucion_roles=distribucion_roles,
                         usuarios_activos=usuarios_activos,
                         selected_period=selected_period,
                         show_all=show_all)


@bp.route('/api/recent-files')
@login_required
def api_recent_files():
    """Devuelve en JSON el historial de archivos recientes con datos del usuario.
    Acepta 'limit' (int) o 'all=1' para traer todo.
    """
    try:
        all_param = request.args.get('all', '0') in ['1', 'true', 'True']
        if all_param:
            # Modo "traer todo"
            recent_files = get_recent_files_with_users(None)
            total_records = db.session.query(func.count(Archivo.id)).scalar() or 0
            files_data = []
            for archivo, usuario in recent_files:
                files_data.append({
                    'id': archivo.id,
                    'nombre': archivo.nombre,
                    'extension': getattr(archivo, 'extension', None),
                    'tamano': getattr(archivo, 'tamano', None),
                    'fecha_subida': archivo.fecha_subida.isoformat() if getattr(archivo, 'fecha_subida', None) else None,
                    'estado': getattr(archivo, 'estado', None),
                    'dropbox_path': getattr(archivo, 'dropbox_path', None),
                    'categoria': getattr(archivo, 'categoria', None),
                    'subcategoria': getattr(archivo, 'subcategoria', None),
                    'descripcion': getattr(archivo, 'descripcion', None),
                    'usuario': {
                        'id': usuario.id,
                        'username': getattr(usuario, 'username', None),
                        'email': getattr(usuario, 'email', None),
                        'nombre': getattr(usuario, 'nombre', None),
                        'apellido': getattr(usuario, 'apellido', None)
                    }
                })
            return jsonify({
                'success': True,
                'count': len(files_data),
                'files': files_data,
                'pagination': {
                    'page': 1,
                    'per_page': len(files_data) or total_records,
                    'total': total_records,
                    'pages': 1,
                    'has_prev': False,
                    'has_next': False
                }
            })

        # Paginación
        page = request.args.get('page', 1, type=int) or 1
        per_page = request.args.get('per_page', 10, type=int) or 10
        if per_page < 1:
            per_page = 10
        if per_page > 100:
            per_page = 100
        offset = (page - 1) * per_page

        base_query = db.session.query(Archivo, User).join(
            User, Archivo.usuario_id == User.id
        ).order_by(desc(Archivo.fecha_subida))

        total_records = db.session.query(func.count(Archivo.id)).scalar() or 0
        recent_files = base_query.offset(offset).limit(per_page).all()

        files_data = []
        for archivo, usuario in recent_files:
            files_data.append({
                'id': archivo.id,
                'nombre': archivo.nombre,
                'extension': getattr(archivo, 'extension', None),
                'tamano': getattr(archivo, 'tamano', None),
                'fecha_subida': archivo.fecha_subida.isoformat() if getattr(archivo, 'fecha_subida', None) else None,
                'estado': getattr(archivo, 'estado', None),
                'dropbox_path': getattr(archivo, 'dropbox_path', None),
                'categoria': getattr(archivo, 'categoria', None),
                'subcategoria': getattr(archivo, 'subcategoria', None),
                'descripcion': getattr(archivo, 'descripcion', None),
                'usuario': {
                    'id': usuario.id,
                    'username': getattr(usuario, 'username', None),
                    'email': getattr(usuario, 'email', None),
                    'nombre': getattr(usuario, 'nombre', None),
                    'apellido': getattr(usuario, 'apellido', None)
                }
            })

        total_pages = (total_records + per_page - 1) // per_page if per_page else 1

        return jsonify({
            'success': True,
            'count': len(files_data),
            'files': files_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_records,
                'pages': total_pages,
                'has_prev': page > 1,
                'has_next': page < total_pages
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/dashboard/lector')
@login_required
@role_required('lector')
def dashboard_lector():
    """Dashboard específico para lectores"""
    
    # Registrar actividad de acceso al dashboard de lector
    current_user.registrar_actividad('dashboard_lector_access', 'Acceso al dashboard de lector')
    
    # Estadísticas para lectores (solo archivos y carpetas)
    stats = {
        'total_archivos': Archivo.query.count(),
        'total_carpetas': Folder.query.count(),
        'archivos_recientes': Archivo.query.order_by(Archivo.fecha_subida.desc()).limit(10).count()
    }
    
    # Actividad reciente (últimas 5 actividades)
    actividades_recientes = UserActivityLog.query.filter_by(user_id=current_user.id)\
                                                .order_by(desc(UserActivityLog.fecha))\
                                                .limit(5).all()
    
    # Carpetas recientes del usuario (últimas 5)
    carpetas_recientes = Folder.query.filter_by(user_id=current_user.id)\
        .order_by(Folder.fecha_creacion.desc())\
        .limit(5).all()
    
    # Notificaciones no leídas del usuario
    notificaciones = Notification.query.filter_by(user_id=current_user.id, leida=False)\
        .order_by(Notification.fecha_creacion.desc())\
        .limit(5).all()
    
    return render_template('dashboard/lector.html',
                         stats=stats,
                         actividades_recientes=actividades_recientes,
                         carpetas_recientes=carpetas_recientes,
                         notificaciones=notificaciones)

@bp.route('/dashboard/admin/profile')
@login_required
def dashboard_admin_profile():
    """Perfil específico para administradores - usa la misma vista que /profile"""
    # Permitir acceso a administradores y lectores
    if not (current_user.puede_administrar() or current_user.es_lector()):
        flash('No tienes permisos para acceder a esta página.', 'error')
        return redirect(url_for('main.profile'))
    
    current_user.registrar_actividad('profile_view', 'Visualización del perfil de administrador')
    
    # Contar archivos y carpetas del usuario
    total_archivos = Archivo.query.filter_by(usuario_id=current_user.id).count()
    total_carpetas = Folder.query.filter_by(user_id=current_user.id).count()
    
    # Actividad reciente del usuario
    actividades_recientes = UserActivityLog.query.filter_by(user_id=current_user.id)\
                                                .order_by(desc(UserActivityLog.fecha))\
                                                .limit(5).all()
    
    # Obtener beneficiarios del usuario (si es cliente)
    beneficiarios = []
    if current_user.es_cliente():
        beneficiarios = Beneficiario.query.filter_by(titular_id=current_user.id).all()
    
    # Obtener último acceso en zona horaria de Colombia
    last_login_colombia = None
    if current_user.ultimo_acceso:
        from datetime import timedelta
        colombia_offset = timedelta(hours=5)
        last_login_colombia = current_user.ultimo_acceso - colombia_offset
    
    # Paginación para historial de actividad
    page_activity = request.args.get('page_activity', 1, type=int)
    per_page_activity = request.args.get('per_page_activity', 10, type=int)
    
    activity_logs_pagination = UserActivityLog.query.filter_by(user_id=current_user.id)\
        .order_by(desc(UserActivityLog.fecha))\
        .paginate(page=page_activity, per_page=per_page_activity, error_out=False)
    
    form = ProfileForm()
    
    return render_template('profile/view.html',
                         user=current_user,
                         form=form,
                         total_archivos=total_archivos,
                         total_carpetas=total_carpetas,
                         actividades_recientes=actividades_recientes,
                         beneficiarios=beneficiarios,
                         last_login_colombia=last_login_colombia,
                         activity_logs_pagination=activity_logs_pagination)

@bp.route('/api/activity_logs')
@login_required
def api_activity_logs():
    """API para obtener logs de actividad paginados"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    activity_logs_pagination = UserActivityLog.query.filter_by(user_id=current_user.id)\
        .order_by(desc(UserActivityLog.fecha))\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    # Preparar datos para JSON
    logs_data = []
    for log_entry in activity_logs_pagination.items:
        logs_data.append({
            'id': log_entry.id,
            'fecha': log_entry.fecha.isoformat() if log_entry.fecha else None,
            'accion': log_entry.accion,
            'descripcion': log_entry.descripcion,
            'ip_address': log_entry.ip_address
        })
    
    return jsonify({
        'logs': logs_data,
        'pagination': {
            'page': activity_logs_pagination.page,
            'pages': activity_logs_pagination.pages,
            'per_page': activity_logs_pagination.per_page,
            'total': activity_logs_pagination.total,
            'has_prev': activity_logs_pagination.has_prev,
            'has_next': activity_logs_pagination.has_next,
            'prev_num': activity_logs_pagination.prev_num,
            'next_num': activity_logs_pagination.next_num
        }
    })

@bp.route('/logout')
@login_required
def logout():
    """Cerrar sesión del usuario"""
    from flask_login import logout_user
    from flask import session
    
    # Registrar actividad antes de cerrar sesión
    current_user.registrar_actividad('logout', 'Cierre de sesión')
    
    # Limpiar sesión
    session.clear()
    logout_user()
    
    flash('Has cerrado sesión exitosamente.', 'success')
    return redirect(url_for('auth.login'))

@bp.route('/profile')
@login_required
def profile():
    """Ver perfil del usuario actual"""
    
    current_user.registrar_actividad('profile_view', 'Visualización del perfil')

    # Si es admin o lector, usar el perfil de administrador
    if hasattr(current_user, 'puede_administrar') and (current_user.puede_administrar() or (hasattr(current_user, 'es_lector') and current_user.es_lector())):
        return redirect(url_for('main.dashboard_admin_profile'))
    
    # Contar archivos y carpetas del usuario
    total_archivos = Archivo.query.filter_by(usuario_id=current_user.id).count()
    total_carpetas = Folder.query.filter_by(user_id=current_user.id).count()
    
    # Actividad reciente del usuario
    actividades_recientes = UserActivityLog.query.filter_by(user_id=current_user.id)\
                                                .order_by(desc(UserActivityLog.fecha))\
                                                .limit(5).all()
    
    # Obtener beneficiarios del usuario (si es cliente)
    beneficiarios = []
    if current_user.es_cliente():
        beneficiarios = Beneficiario.query.filter_by(titular_id=current_user.id).all()
    
    # Obtener último acceso en zona horaria de Colombia
    last_login_colombia = None
    if current_user.ultimo_acceso:
        from datetime import timedelta
        colombia_offset = timedelta(hours=5)
        last_login_colombia = current_user.ultimo_acceso - colombia_offset
    
    # Paginación para historial de actividad
    page_activity = request.args.get('page_activity', 1, type=int)
    per_page_activity = request.args.get('per_page_activity', 10, type=int)
    
    activity_logs_pagination = UserActivityLog.query.filter_by(user_id=current_user.id)\
        .order_by(desc(UserActivityLog.fecha))\
        .paginate(page=page_activity, per_page=per_page_activity, error_out=False)
    
    form = ProfileForm()
    # Listas para selects
    from app.utils.countries import get_nationalities_list
    nationalities = get_nationalities_list()
    
    return render_template('profile/view.html',
                         user=current_user,
                         form=form,
                         nationalities=nationalities,
                         total_archivos=total_archivos,
                         total_carpetas=total_carpetas,
                         actividades_recientes=actividades_recientes,
                         beneficiarios=beneficiarios,
                         last_login_colombia=last_login_colombia,
                         activity_logs_pagination=activity_logs_pagination)

@bp.route('/profile', methods=['POST'])
@login_required
def profile_update():
    """Actualizar perfil del usuario"""
    try:
        is_ajax = (
            request.is_json
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.accept_mimetypes.best == 'application/json'
        )

        # Aceptar JSON (fetch) y también form posts (fallback), evitando 415 Unsupported Media Type
        data = request.get_json(silent=True)
        if data is None:
            data = request.form.to_dict(flat=True) if request.form else {}

        if not isinstance(data, dict):
            data = {}
        
        # Validación temprana de cambio de contraseña (antes de cualquier actualización)
        intento_cambio_password = any([
            bool(data.get('old_password')),
            bool(data.get('new_password')),
            bool(data.get('confirm_password'))
        ])
        
        if intento_cambio_password:
            old_password = data.get('old_password') or ''
            new_password = data.get('new_password') or ''
            confirm_password = data.get('confirm_password') or ''
            
            # Todos los campos requeridos
            if not old_password or not new_password or not confirm_password:
                return jsonify({'error': 'Para cambiar la contraseña, completa los tres campos.'}), 400
            
            # Validar contraseña actual
            if not current_user.check_password(old_password):
                return jsonify({'error': 'La contraseña actual es incorrecta'}), 400
            
            # Validar coincidencia
            if new_password != confirm_password:
                return jsonify({'error': 'La nueva contraseña y la confirmación no coinciden'}), 400
            
            # Validar longitud mínima
            if len(new_password) < 6:
                return jsonify({'error': 'La nueva contraseña debe tener al menos 6 caracteres.'}), 400
        
        # Actualizar información personal
        if 'nombre' in data:
            current_user.nombre = data['nombre']
        if 'apellido' in data:
            current_user.apellido = data['apellido']
        if 'email' in data:
            current_user.email = data['email']
        if 'telefono' in data:
            current_user.telefono = data['telefono']
        if 'fecha_nacimiento' in data and data['fecha_nacimiento']:
            current_user.fecha_nacimiento = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
        if 'nacionalidad' in data:
            current_user.nacionality = data['nacionalidad']
        
        # Actualizar información de dirección
        if 'direccion' in data:
            current_user.direccion = data['direccion']
        if 'ciudad' in data:
            current_user.ciudad = data['ciudad']
        if 'estado' in data:
            current_user.estado = data['estado']
        if 'codigo_postal' in data:
            current_user.codigo_postal = data['codigo_postal']
        if 'pais' in data:
            current_user.country = data['pais']
        
        # Guardar área libremente en DB (texto)
        if 'area' in data:
            current_user.area = (data.get('area') or '').strip() or None

        # Cambiar contraseña si se validó intento de cambio
        if intento_cambio_password:
            current_user.set_password(data['new_password'])
            message = 'Perfil y contraseña actualizados exitosamente. Serás redirigido al login.'
        else:
            message = 'Perfil actualizado exitosamente.'
        
        db.session.commit()
        
        # Registrar actividad
        current_user.registrar_actividad('profile_update', 'Actualización del perfil')
        
        if is_ajax:
            return jsonify({'message': message}), 200
        flash(message, 'success')
        return redirect(url_for('main.profile'))
        
    except Exception as e:
        db.session.rollback()
        if (
            request.is_json
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.accept_mimetypes.best == 'application/json'
        ):
            return jsonify({'error': f'Error al actualizar perfil: {str(e)}'}), 500
        flash(f'Error al actualizar perfil: {str(e)}', 'error')
        return redirect(url_for('main.profile'))

@bp.route('/profile/editar_beneficiario', methods=['POST'])
@login_required
def editar_beneficiario():
    """Editar beneficiario"""
    try:
        beneficiary_id = request.form.get('beneficiary_id')
        name = request.form.get('name')
        lastname = request.form.get('lastname')
        nationality = request.form.get('nationality')
        birth_date = request.form.get('birth_date')
        
        if not all([beneficiary_id, name, lastname, nationality, birth_date]):
            flash('Todos los campos son obligatorios', 'error')
            return redirect(url_for('main.profile'))
        
        # Verificar que el beneficiario pertenece al usuario actual
        beneficiario = Beneficiario.query.filter_by(
            id=beneficiary_id, 
            titular_id=current_user.id
        ).first()
        
        if not beneficiario:
            flash('Beneficiario no encontrado', 'error')
            return redirect(url_for('main.profile'))
        
        # Actualizar datos
        beneficiario.nombre = name
        beneficiario.lastname = lastname
        beneficiario.nationality = nationality
        beneficiario.fecha_nacimiento = datetime.strptime(birth_date, '%Y-%m-%d').date()
        
        db.session.commit()
        
        # Registrar actividad
        current_user.registrar_actividad('beneficiary_update', f'Actualizó beneficiario {name} {lastname}')
        
        return redirect(url_for('main.profile'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar beneficiario: {str(e)}', 'error')
        return redirect(url_for('main.profile'))

@bp.route('/listar_carpetas')
@login_required
def listar_carpetas():
    """Listar carpetas de usuarios - para administradores y lectores"""
    
    # Permitir acceso a administradores y lectores
    if not (current_user.puede_administrar() or current_user.es_lector()):
        flash('No tienes permisos para acceder a esta página.', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Parámetros de búsqueda
    busqueda = request.args.get('q', '').strip()
    
    # Query base
    query = User.query
    
    # Filtrar usuarios según el rol del usuario actual
    if current_user.es_lector():
        # Los lectores solo pueden ver usuarios con rol 'cliente'
        query = query.filter(User.rol == 'cliente')
    # Los administradores pueden ver todos los usuarios
    
    # Aplicar filtro de búsqueda si se proporciona
    if busqueda:
        query = query.filter(
            db.or_(
                User.nombre.ilike(f'%{busqueda}%'),
                User.apellido.ilike(f'%{busqueda}%'),
                User.email.ilike(f'%{busqueda}%')
            )
        )
    
    # Obtener usuarios
    usuarios = query.all()
    
    # Contar carpetas por usuario
    carpetas_por_usuario = {}
    for usuario in usuarios:
        carpetas_por_usuario[usuario.id] = Folder.query.filter_by(user_id=usuario.id).count()
    
    # Usar el mismo template para admin y lector
    return render_template('admin/listar_carpetas.html',
                         usuarios=usuarios,
                         carpetas_por_usuario=carpetas_por_usuario,
                         busqueda=busqueda)

@bp.route('/listar_usuarios_admin')
@login_required
@role_required('admin')
def listar_usuarios_admin():
    """Página de administración de usuarios administrativos (Admin, Lector, SuperAdmin)"""
    
    # Parámetros de búsqueda y filtros
    busqueda = request.args.get('q', '').strip()
    rol_filtro = request.args.get('rol', '')
    estado_filtro = request.args.get('estado', '')
    page = request.args.get('page', 1, type=int)
    # Mostrar 10 notificaciones por página
    per_page = 10
    
    # Query base - SOLO usuarios administrativos (admin, lector, superadmin)
    query = User.query.filter(User.rol.in_(['admin', 'lector', 'superadmin']))
    
    # Aplicar filtros
    if busqueda:
        query = query.filter(
            db.or_(
                User.nombre.ilike(f'%{busqueda}%'),
                User.apellido.ilike(f'%{busqueda}%'),
                User.email.ilike(f'%{busqueda}%')
            )
        )
    
    if rol_filtro:
        query = query.filter(User.rol == rol_filtro)
    
    if estado_filtro == 'activo':
        query = query.filter(User.activo == True)
    elif estado_filtro == 'inactivo':
        query = query.filter(User.activo == False)
    
    # Paginación
    usuarios = query.order_by(User.nombre).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Estadísticas para cada usuario
    estadisticas_usuarios = {}
    for usuario in usuarios.items:
        estadisticas_usuarios[usuario.id] = {
            'archivos': Archivo.query.filter_by(usuario_id=usuario.id).count(),
            'carpetas': Folder.query.filter_by(user_id=usuario.id).count(),
            'beneficiarios': Beneficiario.query.filter_by(titular_id=usuario.id).count(),
            'ultimo_acceso': usuario.ultimo_acceso
        }
    
    return render_template('admin/usuarios.html',
                         usuarios=usuarios,
                         estadisticas_usuarios=estadisticas_usuarios,
                         busqueda=busqueda,
                         rol_filtro=rol_filtro,
                         estado_filtro=estado_filtro)

@bp.route('/notificaciones')
@login_required
def notificaciones():
    """Compat: redirige a la nueva página de historial de notificaciones"""
    return redirect(url_for('main.ver_notificaciones'))

@bp.route('/notificaciones/<int:notif_id>/marcar_leida', methods=['POST'])
@login_required
def marcar_notificacion_leida(notif_id):
    """Marcar una notificación como leída"""
    
    notificacion = Notification.query.filter_by(
        id=notif_id, user_id=current_user.id
    ).first_or_404()
    
    notificacion.marcar_como_leida()
    
    return jsonify({'success': True})

@bp.route('/api/notificaciones/no_leidas')
@login_required
def api_notificaciones_no_leidas():
    """API para obtener el número de notificaciones no leídas"""
    
    count = Notification.query.filter_by(user_id=current_user.id, leida=False).count()
    return jsonify({'count': count}) 

@bp.route('/admin/carpetas')
@login_required
@role_required('admin')
def listar_carpetas_admin():
    """Lista de todas las carpetas del sistema para administradores"""
    # Obtener todas las carpetas con información de usuario
    carpetas = db.session.query(Folder, User)\
        .join(User, Folder.user_id == User.id)\
        .order_by(Folder.fecha_creacion.desc()).all()
    
    # Registrar actividad
    current_user.registrar_actividad('admin_carpetas_view', 'Acceso a gestión de carpetas')
    
    return render_template('admin/listar_carpetas.html', carpetas=carpetas)

@bp.route('/admin/system-settings')
@login_required
@role_required('superadmin')
def system_settings():
    """Configuración del sistema - solo para super administradores"""
    # Solo super administradores pueden acceder
    settings = SystemSettings.query.all()
    
    # Registrar actividad
    current_user.registrar_actividad('system_settings_access', 'Acceso a configuración del sistema')
    
    return render_template('admin/system_settings.html', settings=settings)

# Rutas API para la gestión de usuarios administrativos
@bp.route('/api/usuarios/<int:usuario_id>/historial')
@login_required
@role_required('admin')
def api_usuario_historial(usuario_id):
    """API para obtener el historial de actividad de un usuario"""
    try:
        usuario = User.query.get_or_404(usuario_id)
        
        # Verificar que el usuario sea administrativo
        if usuario.rol not in ['admin', 'lector', 'superadmin']:
            return jsonify({'error': 'Acceso denegado'}), 403
        
        # Obtener actividades del usuario
        actividades = UserActivityLog.query.filter_by(user_id=usuario_id)\
            .order_by(desc(UserActivityLog.fecha))\
            .limit(50).all()
        
        # Mapeo de códigos de acción a etiquetas en español
        accion_labels = {
            'login': 'Inicio de sesión',
            'logout': 'Cierre de sesión',
            'profile_view': 'Vista de perfil',
            'profile_update': 'Actualización de perfil',
            'user_registered': 'Usuario registrado',
            'registration_completed': 'Registro completado',
            'password_changed': 'Cambio de contraseña',
            'password_reset': 'Restablecimiento de contraseña',
            'user_status_changed': 'Cambio de estado de usuario',
            'user_role_changed': 'Cambio de rol de usuario',
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
                'ip_address': actividad.ip_address
            })
        
        return jsonify({
            'success': True,
            'usuario': {
                'id': usuario.id,
                'nombre': usuario.nombre_completo,
                'email': usuario.email,
                'rol': usuario.rol
            },
            'actividades': actividades_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/usuarios/<int:usuario_id>/datos')
@login_required
@role_required('admin')
def api_usuario_datos(usuario_id):
    """API para obtener los datos de un usuario"""
    try:
        usuario = User.query.get_or_404(usuario_id)
        
        # Verificar que el usuario sea administrativo
        if usuario.rol not in ['admin', 'lector', 'superadmin']:
            return jsonify({'error': 'Acceso denegado'}), 403
        
        return jsonify({
            'success': True,
            'usuario': {
                'id': usuario.id,
                'nombre': usuario.nombre,
                'apellido': usuario.apellido,
                'email': usuario.email,
                'rol': usuario.rol,
                'activo': usuario.activo,
                'fecha_registro': usuario.fecha_registro.isoformat() if usuario.fecha_registro else None,
                'ultimo_acceso': usuario.ultimo_acceso.isoformat() if usuario.ultimo_acceso else None
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/test')
def api_test():
    """API de prueba para verificar que el servidor funciona"""
    return jsonify({
        'success': True,
        'message': 'API funcionando correctamente',
        'timestamp': datetime.utcnow().isoformat()
    })

@bp.route('/api/usuarios/<int:usuario_id>/datos_completos')
@login_required
@role_required('admin')
def api_usuario_datos_completos(usuario_id):
    """API para obtener los datos completos de un usuario con roles y permisos"""
    try:
        usuario = User.query.get_or_404(usuario_id)
        
        # Verificar que el usuario sea administrativo
        if usuario.rol not in ['admin', 'lector', 'superadmin']:
            return jsonify({'error': 'Acceso denegado'}), 403
        
        # Definir roles disponibles
        all_roles = [
            {
                'slug': 'admin',
                'name': 'Administrador',
                'description': 'Acceso completo al sistema con gestión de usuarios y archivos'
            },
            {
                'slug': 'lector',
                'name': 'Lector',
                'description': 'Acceso de solo lectura con permisos adicionales configurables'
            },
            {
                'slug': 'superadmin',
                'name': 'Super Administrador',
                'description': 'Acceso total al sistema incluyendo configuración del sistema'
            }
        ]
        
        # Obtener permisos adicionales del lector si existen
        lector_extra_permissions = []
        if hasattr(usuario, 'lector_extra_permissions') and usuario.lector_extra_permissions:
            if isinstance(usuario.lector_extra_permissions, str):
                lector_extra_permissions = [perm.strip() for perm in usuario.lector_extra_permissions.split(',') if perm.strip()]
            else:
                lector_extra_permissions = usuario.lector_extra_permissions
        
        # Preparar datos del usuario de forma segura
        usuario_data = {
            'id': usuario.id,
            'nombre': usuario.nombre or '',
            'apellido': usuario.apellido or '',
            'email': usuario.email or '',
            'rol': usuario.rol or 'admin',
            'activo': usuario.activo if hasattr(usuario, 'activo') else True,
            'fecha_registro': usuario.fecha_registro.isoformat() if usuario.fecha_registro else None,
            'ultimo_acceso': usuario.ultimo_acceso.isoformat() if usuario.ultimo_acceso else None,
            'telefono': usuario.telefono if hasattr(usuario, 'telefono') else None,
            'direccion': usuario.direccion if hasattr(usuario, 'direccion') else None,
            'ciudad': usuario.ciudad if hasattr(usuario, 'ciudad') else None,
            'estado': usuario.estado if hasattr(usuario, 'estado') else None,
            'codigo_postal': usuario.codigo_postal if hasattr(usuario, 'codigo_postal') else None,
            'fecha_nacimiento': usuario.fecha_nacimiento.isoformat() if hasattr(usuario, 'fecha_nacimiento') and usuario.fecha_nacimiento else None,
            'nacionalidad': usuario.nacionality if hasattr(usuario, 'nacionality') else None,
            'lector_extra_permissions': lector_extra_permissions
        }
        
        return jsonify({
            'success': True,
            'usuario': usuario_data,
            'all_roles': all_roles
        })
        
    except Exception as e:
        print(f"Error en api_usuario_datos_completos: {str(e)}")  # Debug
        return jsonify({'error': str(e)}), 500

@bp.route('/api/usuarios/<int:usuario_id>/actualizar', methods=['POST'])
@login_required
@role_required('admin')
def api_usuario_actualizar(usuario_id):
    """API para actualizar los datos de un usuario"""
    try:
        usuario = User.query.get_or_404(usuario_id)
        
        # Verificar que el usuario sea administrativo
        if usuario.rol not in ['admin', 'lector', 'superadmin']:
            return jsonify({'error': 'Acceso denegado'}), 403
        
        # Información básica
        nombre = request.form.get('name', '').strip()
        apellido = request.form.get('lastname', '').strip()
        email = request.form.get('email', '').strip()
        fecha_nacimiento = request.form.get('date_of_birth')
        nacionalidad = request.form.get('nationality', '').strip()
        
        # Información de contacto
        telefono = request.form.get('telephone', '').strip()
        direccion = request.form.get('address', '').strip()
        ciudad = request.form.get('city', '').strip()
        estado = request.form.get('state', '').strip()
        codigo_postal = request.form.get('zip_code', '').strip()
        
        # Roles y estado
        rol = request.form.get('rol', 'admin')
        # Si 'activo' no llega en el formulario, por defecto mantener al usuario ACTIVO
        activo_value = request.form.get('activo')
        activo = True if activo_value is None else (activo_value == 'on')
        
        # Contraseña (opcional)
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        
        # Validaciones básicas
        if not email:
            return jsonify({'error': 'El email es obligatorio'}), 400
        
        if not rol in ['admin', 'lector', 'superadmin']:
            return jsonify({'error': 'Rol no válido'}), 400
        
        if password and password != password_confirm:
            return jsonify({'error': 'Las contraseñas no coinciden'}), 400
        
        # Verificar si el email ya existe (excluyendo el usuario actual)
        email_existente = User.query.filter(
            User.email == email,
            User.id != usuario_id
        ).first()
        
        if email_existente:
            return jsonify({'error': 'El email ya está en uso'}), 400
        
        # Actualizar datos básicos del usuario
        usuario.nombre = nombre
        usuario.apellido = apellido
        usuario.email = email
        usuario.rol = rol
        usuario.activo = activo
        
        # Actualizar campos adicionales si existen en el modelo
        if hasattr(usuario, 'fecha_nacimiento'):
            usuario.fecha_nacimiento = fecha_nacimiento if fecha_nacimiento else None
        if hasattr(usuario, 'nacionalidad'):
            usuario.nacionalidad = nacionalidad
        if hasattr(usuario, 'telefono'):
            usuario.telefono = telefono
        if hasattr(usuario, 'direccion'):
            usuario.direccion = direccion
        if hasattr(usuario, 'ciudad'):
            usuario.ciudad = ciudad
        if hasattr(usuario, 'estado'):
            usuario.estado = estado
        if hasattr(usuario, 'codigo_postal'):
            usuario.codigo_postal = codigo_postal
        
        # Actualizar permisos adicionales del lector
        lector_extra_permissions = request.form.getlist('lector_extra_permissions')
        permissions_changed = False
        
        if hasattr(usuario, 'lector_extra_permissions'):
            current_permissions = []
            if usuario.lector_extra_permissions:
                current_permissions = usuario.lector_extra_permissions.split(',') if isinstance(usuario.lector_extra_permissions, str) else usuario.lector_extra_permissions
            
            # Verificar si los permisos cambiaron
            if set(current_permissions) != set(lector_extra_permissions):
                permissions_changed = True
            
            if lector_extra_permissions:
                usuario.lector_extra_permissions = ','.join(lector_extra_permissions)
            else:
                usuario.lector_extra_permissions = None
        
        # Actualizar contraseña si se proporcionó
        if password:
            usuario.set_password(password)
        
        # Registrar la actividad
        current_user.registrar_actividad(
            'usuario_actualizado',
            f'Actualizó información del usuario {usuario.email}'
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Usuario actualizado correctamente',
            'permissions_changed': permissions_changed
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/api/usuarios/<int:usuario_id>/eliminar', methods=['POST'])
@login_required
@role_required('admin')
def api_usuario_eliminar(usuario_id):
    """API para eliminar un usuario"""
    try:
        usuario = User.query.get_or_404(usuario_id)
        
        # Verificar que el usuario sea administrativo
        if usuario.rol not in ['admin', 'lector', 'superadmin']:
            return jsonify({'error': 'Acceso denegado'}), 403
        
        # No permitir eliminar el usuario actual
        if usuario.id == current_user.id:
            return jsonify({'error': 'No puedes eliminar tu propia cuenta'}), 400
        
        # Verificar si el usuario tiene archivos o carpetas
        archivos_count = Archivo.query.filter_by(usuario_id=usuario_id).count()
        carpetas_count = Folder.query.filter_by(user_id=usuario_id).count()
        
        if archivos_count > 0 or carpetas_count > 0:
            return jsonify({
                'error': f'No se puede eliminar el usuario. Tiene {archivos_count} archivos y {carpetas_count} carpetas asociadas.'
            }), 400
        
        # Registrar la actividad antes de eliminar
        current_user.registrar_actividad(
            'usuario_eliminado',
            f'Eliminó al usuario {usuario.email}'
        )
        
        # Eliminar el usuario
        db.session.delete(usuario)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Usuario eliminado correctamente'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500 

@bp.route('/config/dropbox/status')
@login_required
@role_required('admin')
def dropbox_config_status():
    """Página de estado y configuración de Dropbox"""
    from app.dropbox_token_manager import get_token_manager
    import os
    
    try:
        # Obtener información del gestor de tokens
        manager = get_token_manager()
        status = manager.get_token_status()
        
        # Obtener validación completa de tokens
        from app.dropbox_token_manager import validate_dropbox_tokens
        validation_status = validate_dropbox_tokens()
        
        # Estado de conexión con Dropbox basado en validación
        if validation_status["access_token_valid"] and validation_status["refresh_token_valid"]:
            dropbox_status = "✅ Conectado correctamente - Todos los tokens son válidos"
        elif validation_status["access_token_valid"]:
            dropbox_status = "⚠️ Conectado - Access token válido, pero refresh token tiene problemas"
        elif validation_status["errors"]:
            dropbox_status = f"❌ Error de conexión: {'; '.join(validation_status['errors'])}"
        else:
            dropbox_status = "⚠️ Estado desconocido - Verificando tokens..."
        
        # Variables de entorno con valores parciales (solo mostrar si están configuradas)
        config_status = {}
        
        # DROPBOX_API_KEY (token de acceso)
        api_key = os.environ.get('DROPBOX_API_KEY') or os.environ.get('DROPBOX_ACCESS_TOKEN')
        config_status['DROPBOX_API_KEY'] = {
            'configurado': bool(api_key),
            'valor': f"{api_key[:10]}..." if api_key else "No configurado"
        }
        
        # DROPBOX_APP_KEY
        app_key = os.environ.get('DROPBOX_APP_KEY')
        config_status['DROPBOX_APP_KEY'] = {
            'configurado': bool(app_key),
            'valor': f"{app_key[:10]}..." if app_key else "No configurado"
        }
        
        # DROPBOX_APP_SECRET
        app_secret = os.environ.get('DROPBOX_APP_SECRET')
        config_status['DROPBOX_APP_SECRET'] = {
            'configurado': bool(app_secret),
            'valor': f"{app_secret[:10]}..." if app_secret else "No configurado"
        }
        
        # DROPBOX_ACCESS_TOKEN
        access_token = os.environ.get('DROPBOX_ACCESS_TOKEN')
        config_status['DROPBOX_ACCESS_TOKEN'] = {
            'configurado': bool(access_token),
            'valor': f"{access_token[:10]}..." if access_token else "No configurado"
        }
        
        # DROPBOX_REFRESH_TOKEN
        refresh_token = os.environ.get('DROPBOX_REFRESH_TOKEN')
        config_status['DROPBOX_REFRESH_TOKEN'] = {
            'configurado': bool(refresh_token),
            'valor': f"{refresh_token[:10]}..." if refresh_token else "No configurado"
        }
        
        # Verificar si todas están configuradas
        todas_configuradas = all(var['configurado'] for var in config_status.values())
        
        # Sistema de renovación automática
        auto_refresh_enabled = status.get('refresh_token_configured', False)
        
        # Información de renovación
        last_refresh = None
        next_refresh = None
        
        if hasattr(manager, 'last_refresh') and manager.last_refresh:
            from datetime import timedelta
            last_refresh = manager.last_refresh.strftime('%Y-%m-%d %H:%M:%S')
            next_refresh = (manager.last_refresh + timedelta(minutes=45)).strftime('%Y-%m-%d %H:%M:%S')
        
        return render_template('config_status.html', 
                             config_status=config_status,
                             todas_configuradas=todas_configuradas,
                             dropbox_status=dropbox_status,
                             auto_refresh_enabled=auto_refresh_enabled,
                             last_refresh=last_refresh,
                             next_refresh=next_refresh,
                             validation_status=validation_status)
    except Exception as e:
        logger.error(f"Error en config status: {e}")
        flash(f'Error al obtener estado: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@bp.route('/config/dropbox/refresh', methods=['POST'])
@login_required
@role_required('admin') 
def refresh_dropbox_token():
    """Renovar token de Dropbox manualmente"""
    from app.dropbox_token_manager import refresh_dropbox_token as refresh_token
    
    try:
        success = refresh_token()
        if success:
            print('Token de Dropbox renovado exitosamente', 'success')
        else:
            print('No se pudo renovar el token. Revisa los logs para más detalles.', 'error')
    except Exception as e:
        logger.error(f"Error renovando token: {e}")
        flash(f'Error al renovar token: {str(e)}', 'error')
    
    return redirect(url_for('main.dropbox_config_status'))

@bp.route('/config/dropbox/validate', methods=['GET'])
@login_required
@role_required('admin') 
def validate_dropbox_config():
    """API endpoint para validar configuración de Dropbox"""
    from app.dropbox_token_manager import validate_dropbox_tokens
    
    try:
        validation_status = validate_dropbox_tokens()
        return jsonify({
            "success": True,
            "validation": validation_status
        })
    except Exception as e:
        logger.error(f"Error validando configuración: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/webhook/dropbox', methods=['GET', 'POST'])
def dropbox_webhook():
    """
    Endpoint para manejar webhooks de Dropbox
    
    GET: Verificación del desafío (challenge)
    POST: Notificaciones de cambios en archivos
    """
    print("🔔 Webhook de Dropbox recibido")
    print(f"Método: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    
    if request.method == 'GET':
        # Dropbox envía un desafío para verificar la URL del webhook
        challenge = request.args.get('challenge')
        print(f"Desafío recibido: {challenge}")
        
        if challenge:
            # Responder con el mismo valor del desafío
            print(f"Respondiendo al desafío: {challenge}")
            return challenge, 200, {'Content-Type': 'text/plain'}
        else:
            print("No se recibió parámetro de desafío")
            return "No challenge parameter", 400
    
    elif request.method == 'POST':
        # Procesar notificaciones de cambios en Dropbox
        try:
            # Verificar que el contenido sea JSON
            if not request.is_json:
                print("Error: El contenido no es JSON válido")
                return "Invalid JSON", 400
            
            data = request.get_json()
            print(f"Datos del webhook: {data}")
            
            # Verificar que el webhook es de Dropbox
            if 'list_folder' not in data:
                print("Error: No es un webhook válido de Dropbox")
                return "Invalid webhook", 400
            
            # Procesar el webhook usando las funciones de utilidad
            from app.dropbox_utils import process_dropbox_webhook
            success = process_dropbox_webhook(data)
            
            if success:
                print("Webhook procesado exitosamente")
                return "OK", 200
            else:
                print("Error procesando webhook")
                return "Error processing webhook", 500
            
        except Exception as e:
            print(f"Error procesando webhook: {e}")
            return "Internal Server Error", 500
    
    else:
        return "Method not allowed", 405 

@bp.route('/test/webhook', methods=['GET'])
def test_webhook():
    """
    Ruta de prueba para verificar que el webhook funciona correctamente
    """
    challenge = "test_challenge_12345"
    print(f"Prueba de webhook - Desafío: {challenge}")
    
    # Simular la respuesta que debería dar el webhook
    return f"""
    <html>
    <head><title>Test Webhook</title></head>
    <body>
        <h1>Test Webhook de Dropbox</h1>
        <p>Esta es una página de prueba para verificar que el webhook funciona.</p>
        <p>Si Dropbox envía un desafío, debería responder con: <strong>{challenge}</strong></p>
        <hr>
        <p><strong>URL del webhook:</strong> https://micaso.inmigracionokabogados.com/webhook/dropbox</p>
        <p><strong>Método:</strong> GET (para desafío) / POST (para notificaciones)</p>
    </body>
    </html>
    """ 


@bp.route('/debug/file-extensions')
@login_required
@role_required('admin')
def debug_file_extensions_route():
    """Ruta temporal para debug de extensiones de archivo"""
    from app.utils.dashboard_stats import debug_file_extensions, get_file_types_stats
    
    # Ejecutar debug
    results = debug_file_extensions()
    
    # Obtener estadísticas generales
    general_stats = get_file_types_stats()
    
    # Obtener estadísticas del mes actual
    from app.utils.dashboard_stats import calculate_period_dates
    start_date, end_date = calculate_period_dates('month')
    month_stats = get_file_types_stats(start_date, end_date)
    
    return jsonify({
        'debug_results': [(str(ext), count) for ext, count in results],
        'general_stats': general_stats,
        'month_stats': month_stats,
        'total_files': sum([count for _, count in results])
    })


# Endpoints para notificaciones
@bp.route('/api/notificaciones', methods=['GET'])
@login_required
def obtener_notificaciones():
    """Obtiene las notificaciones no leídas del usuario actual"""
    try:
        notificaciones = obtener_notificaciones_no_leidas(current_user.id)
        
        # Preparar datos para JSON
        notificaciones_data = []
        for notif in notificaciones:
            datos = {
                'id': notif.id,
                'titulo': notif.titulo,
                'mensaje': notif.mensaje,
                'tipo': notif.tipo,
                'fecha_creacion': notif.fecha_creacion.strftime('%d/%m/%Y %H:%M'),
                'leida': notif.leida,
                'archivo_id': notif.archivo_id
            }
            
            # Si hay un archivo asociado, agregar información adicional
            if notif.archivo:
                datos['archivo_nombre'] = notif.archivo.nombre
                datos['archivo_categoria'] = notif.archivo.categoria
            
            notificaciones_data.append(datos)
        
        return jsonify({
            'success': True,
            'notificaciones': notificaciones_data,
            'total': len(notificaciones_data)
        })
    except Exception as e:
        current_app.logger.error(f"Error al obtener notificaciones: {e}")
        return jsonify({
            'success': False,
            'error': 'Error al cargar notificaciones'
        }), 500


@bp.route('/api/notificaciones/ultimas', methods=['GET'])
@login_required
def obtener_ultimas_notificaciones():
    """Obtiene notificaciones del usuario actual con soporte de paginación (page/per_page).

    Si no se provee paginación, respeta "limit" para compatibilidad.
    """
    try:
        from app.models import Notification
        q = Notification.query \
            .filter_by(user_id=current_user.id) \
            .order_by(Notification.fecha_creacion.desc())

        # Soporta page/per_page. Si no vienen, usa "limit" como compatibilidad.
        page = request.args.get('page', type=int)
        per_page = request.args.get('per_page', type=int)
        if page and per_page:
            pagination = q.paginate(page=page, per_page=per_page, error_out=False)
            items = pagination.items
            total = pagination.total
            meta = {
                'page': pagination.page,
                'pages': pagination.pages,
                'has_prev': pagination.has_prev,
                'has_next': pagination.has_next,
                'prev_num': pagination.prev_num if pagination.has_prev else None,
                'next_num': pagination.next_num if pagination.has_next else None,
                'per_page': pagination.per_page,
                'total': total,
            }
        else:
            try:
                limit = int(request.args.get('limit', '5'))
            except Exception:
                limit = 5
            items = q.limit(limit).all()
            total = len(items)
            meta = {
                'page': 1,
                'pages': 1,
                'has_prev': False,
                'has_next': False,
                'prev_num': None,
                'next_num': None,
                'per_page': limit,
                'total': total,
            }

        data = []
        for n in items:
            item = {
                'id': n.id,
                'titulo': n.titulo,
                'mensaje': n.mensaje,
                'tipo': n.tipo,
                'leida': n.leida,
                'fecha_creacion': n.fecha_creacion.strftime('%d/%m/%Y %H:%M'),
                'archivo_id': getattr(n, 'archivo_id', None)
            }
            if getattr(n, 'archivo', None):
                item['archivo_nombre'] = n.archivo.nombre
                item['archivo_categoria'] = n.archivo.categoria
            data.append(item)

        response = jsonify({'success': True, 'notificaciones': data, **meta})
        # Headers anti-caché para asegurar datos frescos
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        current_app.logger.exception('Error al obtener ultimas notificaciones')
        response = jsonify({'success': False, 'error': 'Error al cargar notificaciones'})
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response, 500


@bp.route('/notificaciones/historial', methods=['GET'])
@login_required
def ver_notificaciones():
    """Página con el historial completo de notificaciones del usuario actual (paginado)."""
    from app.models import Notification
    try:
        page = int(request.args.get('page', '1'))
    except Exception:
        page = 1
    # Mostrar 10 notificaciones por página
    per_page = 10

    q = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.fecha_creacion.desc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'notificaciones.html',
        notificaciones=pagination.items,
        pagination=pagination,
        user_role=getattr(current_user, 'rol', None)
    )

@bp.route('/api/notificaciones/count', methods=['GET'])
@login_required
def contar_notificaciones():
    """Cuenta las notificaciones no leídas del usuario actual"""
    try:
        count = contar_notificaciones_no_leidas(current_user.id)
        response = jsonify({
            'success': True,
            'count': count
        })
        # Headers anti-caché para asegurar datos frescos
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        current_app.logger.error(f"Error al contar notificaciones: {e}")
        response = jsonify({
            'success': False,
            'error': 'Error al contar notificaciones'
        })
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response, 500


@bp.route('/api/notificaciones/<int:notif_id>/marcar_leida', methods=['POST'])
@login_required
def marcar_notif_leida(notif_id):
    """Marca una notificación específica como leída"""
    try:
        success = marcar_notificacion_leida(notif_id, current_user.id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Notificación marcada como leída'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Notificación no encontrada o ya está leída'
            }), 404
            
    except Exception as e:
        current_app.logger.error(f"Error al marcar notificación como leída: {e}")
        return jsonify({
            'success': False,
            'error': 'Error al procesar la solicitud'
        }), 500


@bp.route('/api/notificaciones/marcar_todas_leidas', methods=['POST'])
@login_required
def marcar_todas_notif_leidas():
    """Marca todas las notificaciones del usuario como leídas"""
    try:
        success = marcar_todas_notificaciones_leidas(current_user.id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Todas las notificaciones marcadas como leídas'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Error al marcar las notificaciones'
            }), 500
            
    except Exception as e:
        current_app.logger.error(f"Error al marcar todas las notificaciones como leídas: {e}")
        return jsonify({
            'success': False,
            'error': 'Error al procesar la solicitud'
        }), 500 


@bp.route('/api/diag/notificaciones', methods=['GET'])
@login_required
def diag_notificaciones():
    """Diagnóstico rápido de notificaciones/actividades y base de datos en uso."""
    try:
        from sqlalchemy import func
        from app.models import Notification, Archivo, UserActivityLog

        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')

        # Conteos principales
        notif_count = Notification.query.filter_by(user_id=current_user.id).count()
        notif_unread = Notification.query.filter_by(user_id=current_user.id, leida=False).count()
        last_notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.fecha_creacion.desc()).limit(5).all()

        # Actividades recientes
        recent_activities = UserActivityLog.query.filter_by(user_id=current_user.id).order_by(UserActivityLog.fecha.desc()).limit(5).all()

        # Archivos recientes (últimas 24h)
        from datetime import datetime, timedelta
        since = datetime.utcnow() - timedelta(hours=24)
        archivos_24h = Archivo.query.filter(Archivo.fecha_subida >= since).count()

        return jsonify({
            'success': True,
            'db_uri': db_uri,
            'current_user': {
                'id': current_user.id,
                'rol': getattr(current_user, 'rol', None),
                'email': getattr(current_user, 'email', None)
            },
            'notifications': {
                'total_for_user': notif_count,
                'unread_for_user': notif_unread,
                'last_5': [
                    {
                        'id': n.id,
                        'titulo': n.titulo,
                        'archivo_id': n.archivo_id,
                        'fecha_creacion': n.fecha_creacion.isoformat(timespec='seconds')
                    } for n in last_notifs
                ]
            },
            'activities': [
                {
                    'id': a.id,
                    'accion': a.accion,
                    'descripcion': a.descripcion,
                    'fecha': a.fecha.isoformat(timespec='seconds') if a.fecha else None
                } for a in recent_activities
            ],
            'files': {
                'uploaded_last_24h': archivos_24h
            }
        })
    except Exception as e:
        current_app.logger.exception('Error en diagnóstico de notificaciones')
        return jsonify({'success': False, 'error': str(e)}), 500
