from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash

from app import db
from app.models import User, Folder, Archivo, UserActivityLog, Notification, Beneficiario, SystemSettings
from forms import ProfileForm
from app.routes.auth import role_required

bp = Blueprint('main', __name__)

@bp.route('/auth', methods=['GET', 'POST'])
def auth_direct():
    """Ruta directa para /auth que muestra el login sin redirección"""
    from app.routes.auth import login
    return login()

@bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard principal - redirige según el rol"""
    
    # Registrar actividad de acceso al dashboard
    current_user.registrar_actividad('dashboard_access', 'Acceso al dashboard principal')
    
    if current_user.es_cliente():
        return redirect(url_for('main.dashboard_cliente'))
    elif current_user.puede_administrar():
        return redirect(url_for('main.dashboard_admin'))
    else:
        return redirect(url_for('main.dashboard_lector'))

@bp.route('/dashboard/cliente')
@login_required
@role_required('cliente')
def dashboard_cliente():
    """Dashboard específico para clientes"""
    
    # Registrar actividad de acceso al dashboard de cliente
    current_user.registrar_actividad('dashboard_cliente_access', 'Acceso al dashboard de cliente')
    
    # Obtener estadísticas del cliente
    total_archivos = Archivo.query.filter_by(usuario_id=current_user.id).count()
    total_carpetas = Folder.query.filter_by(user_id=current_user.id).count()
    beneficiarios = Beneficiario.query.filter_by(titular_id=current_user.id).count()
    
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
@role_required('admin')
def dashboard_admin():
    """Dashboard específico para administradores"""
    
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
    
    # Obtener el período seleccionado (por defecto 'month')
    period = request.args.get('period', 'month')
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
    
    # Archivos recientes con usuarios
    recent_files = get_recent_files_with_users(10)
    
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
                         selected_period=selected_period)

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

@bp.route('/profile', methods=['POST'])
@login_required
def profile_update():
    """Actualizar perfil del usuario"""
    try:
        data = request.get_json()
        
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
        
        # Cambiar contraseña si se proporcionó
        if data.get('old_password') and data.get('new_password') and data.get('confirm_password'):
            if not current_user.check_password(data['old_password']):
                return jsonify({'error': 'La contraseña actual es incorrecta'}), 400
            
            if data['new_password'] != data['confirm_password']:
                return jsonify({'error': 'La nueva contraseña y la confirmación no coinciden'}), 400
            
            current_user.set_password(data['new_password'])
            message = 'Perfil y contraseña actualizados exitosamente. Serás redirigido al login.'
        else:
            message = 'Perfil actualizado exitosamente.'
        
        db.session.commit()
        
        # Registrar actividad
        current_user.registrar_actividad('profile_update', 'Actualización del perfil')
        
        return jsonify({'message': message}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error al actualizar perfil: {str(e)}'}), 500

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
        
        flash('Beneficiario actualizado exitosamente', 'success')
        return redirect(url_for('main.profile'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar beneficiario: {str(e)}', 'error')
        return redirect(url_for('main.profile'))

@bp.route('/listar_carpetas')
@login_required
def listar_carpetas():
    """Listar carpetas de usuarios - para administradores"""
    
    if not current_user.puede_administrar():
        flash('No tienes permisos para acceder a esta página.', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Obtener todos los usuarios con sus carpetas
    usuarios = User.query.all()
    
    # Contar carpetas por usuario
    carpetas_por_usuario = {}
    for usuario in usuarios:
        carpetas_por_usuario[usuario.id] = Folder.query.filter_by(user_id=usuario.id).count()
    
    return render_template('admin/listar_carpetas.html',
                         usuarios=usuarios,
                         carpetas_por_usuario=carpetas_por_usuario)

@bp.route('/listar_usuarios_admin')
@login_required
@role_required('admin')
def listar_usuarios_admin():
    """Página de administración de usuarios"""
    
    # Parámetros de búsqueda y filtros
    busqueda = request.args.get('q', '').strip()
    rol_filtro = request.args.get('rol', '')
    estado_filtro = request.args.get('estado', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Query base
    query = User.query
    
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
    """Ver notificaciones del usuario"""
    
    # Obtener notificaciones del usuario (paginadas)
    page = request.args.get('page', 1, type=int)
    notificaciones = Notification.query.filter_by(user_id=current_user.id)\
                                      .order_by(desc(Notification.fecha_creacion))\
                                      .paginate(page=page, per_page=10, error_out=False)
    
    return render_template('notifications/list.html', notificaciones=notificaciones)

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