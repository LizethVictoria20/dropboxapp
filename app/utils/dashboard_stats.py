import calendar
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from app.models import User, Archivo, UserActivityLog, Folder, Beneficiario
from app import db


def get_colombia_datetime():
    """Obtiene la fecha y hora actual en zona horaria de Colombia (UTC-5)"""
    utc_now = datetime.utcnow()
    colombia_offset = timedelta(hours=5)
    colombia_now = utc_now - colombia_offset
    return colombia_now


def get_friendly_file_type(extension):
    """Convierte extensiones de archivo a nombres amigables"""
    if not extension:
        return "Desconocido"
    
    extension = extension.lower().replace('.', '')
    
    # Mapeo de extensiones a tipos amigables
    extension_mapping = {
        'pdf': 'PDF',
        'doc': 'Word',
        'docx': 'Word',
        'xls': 'Excel',
        'xlsx': 'Excel',
        'ppt': 'PowerPoint',
        'pptx': 'PowerPoint',
        'jpg': 'Imagen JPG',
        'jpeg': 'Imagen JPG',
        'png': 'Imagen PNG',
        'gif': 'Imagen GIF',
        'bmp': 'Imagen BMP',
        'txt': 'Texto',
        'rtf': 'Texto',
        'zip': 'Comprimido',
        'rar': 'Comprimido',
        '7z': 'Comprimido',
        'mp4': 'Video',
        'avi': 'Video',
        'mov': 'Video',
        'mp3': 'Audio',
        'wav': 'Audio',
        'json': 'JSON',
        'xml': 'XML',
        'html': 'HTML',
        'css': 'CSS',
        'js': 'JavaScript'
    }
    
    return extension_mapping.get(extension, 'Otro')


def calculate_percent_change(current, previous):
    """Calcula el porcentaje de cambio entre dos valores"""
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / previous) * 100, 2)


def calculate_period_dates(period):
    """Calcula las fechas de inicio y fin según el período seleccionado"""
    colombia_now = get_colombia_datetime()
    today_date = colombia_now.date()

    if period == 'today':
        start_datetime = datetime.combine(today_date, datetime.min.time())
        end_datetime = datetime.combine(today_date, datetime.max.time())
    elif period == 'week':
        start_of_week_date = today_date - timedelta(days=today_date.weekday())
        start_datetime = datetime.combine(start_of_week_date, datetime.min.time())
        end_datetime = datetime.combine(today_date, datetime.max.time())
    elif period == 'month':
        start_of_month_date = today_date.replace(day=1)
        start_datetime = datetime.combine(start_of_month_date, datetime.min.time())
        end_datetime = datetime.combine(today_date, datetime.max.time())
    elif period == 'year':
        start_of_year_date = today_date.replace(month=1, day=1)
        start_datetime = datetime.combine(start_of_year_date, datetime.min.time())
        end_datetime = datetime.combine(today_date, datetime.max.time())
    elif period == 'total':
        start_datetime = None
        end_datetime = None
    else:
        # Por defecto, usar el mes actual
        start_of_month_date = today_date.replace(day=1)
        start_datetime = datetime.combine(start_of_month_date, datetime.min.time())
        end_datetime = datetime.combine(today_date, datetime.max.time())

    # Convertir a UTC para las consultas a la base de datos
    if start_datetime:
        utc_offset = timedelta(hours=5)  # Colombia es UTC-5
        start_datetime = start_datetime + utc_offset
        end_datetime = end_datetime + utc_offset

    return start_datetime, end_datetime


def get_file_types_stats(start_date=None, end_date=None):
    """Obtiene estadísticas de tipos de archivo para el período especificado"""
    query = db.session.query(
        Archivo.extension,
        func.count(Archivo.id).label('count')
    )

    if start_date and end_date:
        query = query.filter(
            Archivo.fecha_subida >= start_date,
            Archivo.fecha_subida <= end_date
        )
    
    results = query.group_by(Archivo.extension).all()
    total_count = sum([r.count for r in results])
    
    # Colores personalizados para los tipos de archivo
    colors = [
        '#3a6fb5', '#4c7ebd', '#5a8ac7', '#6495ED', '#779ECB', 
        '#89CFF0', '#9BCDED', '#ADD8E6', '#10B981', '#F59E0B', 
        '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4'
    ]
    
    stats = []
    for i, (extension, count) in enumerate(results):
        friendly_name = get_friendly_file_type(extension)
        percentage = (count / total_count) * 100 if total_count > 0 else 0
        
        stats.append({
            'name': friendly_name,
            'count': count,
            'percentage': round(percentage, 1),
            'color': colors[i % len(colors)]
        })

    # Ordenar por cantidad descendente
    stats.sort(key=lambda x: x['count'], reverse=True)
    return stats


def get_charts_data():
    """Genera datos para los gráficos del dashboard"""
    today = get_colombia_datetime().date()
    
    # Datos para gráfico semanal
    week_data = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        file_count = Archivo.query.filter(func.date(Archivo.fecha_subida) == date).count()
        day_name = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][date.weekday()]
        week_data.append({"label": day_name, "value": file_count})
    
    # Datos para gráfico mensual (por semanas)
    month_data = []
    first_day = today.replace(day=1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    
    for week in range(4):
        start_day = min(week * 7 + 1, days_in_month)
        end_day = min((week + 1) * 7, days_in_month)
        
        start_date = first_day.replace(day=start_day)
        end_date = first_day.replace(day=end_day)
        
        file_count = Archivo.query.filter(
            func.date(Archivo.fecha_subida) >= start_date,
            func.date(Archivo.fecha_subida) <= end_date
        ).count()
        
        month_data.append({"label": f"Sem {week+1}", "value": file_count})
    
    # Datos para gráfico anual (por meses)
    year_data = []
    current_year = today.year
    
    for month in range(1, 13):
        start_date = datetime(current_year, month, 1).date()
        if month == 12:
            end_date = datetime(current_year, month, 31).date()
        else:
            end_date = datetime(current_year, month + 1, 1).date() - timedelta(days=1)
        
        file_count = Archivo.query.filter(
            func.date(Archivo.fecha_subida) >= start_date,
            func.date(Archivo.fecha_subida) <= end_date
        ).count()
        
        month_name = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"][month-1]
        year_data.append({"label": month_name, "value": file_count})
    
    # Datos para gráfico por horas (HOY)
    today_data = []
    today_start = datetime.combine(today, datetime.min.time())
    
    for hour in range(24):
        hour_start = today_start + timedelta(hours=hour)
        hour_end = hour_start + timedelta(hours=1)
        
        # Convertir a UTC para la consulta
        utc_offset = timedelta(hours=5)  # Colombia es UTC-5
        utc_hour_start = hour_start + utc_offset
        utc_hour_end = hour_end + utc_offset
        
        file_count = Archivo.query.filter(
            Archivo.fecha_subida >= utc_hour_start,
            Archivo.fecha_subida < utc_hour_end
        ).count()
        
        hour_label = f"{(hour % 12) or 12}:00 {'PM' if hour >= 12 else 'AM'}"
        today_data.append({"label": hour_label, "value": file_count})
    
    # Datos similares para usuarios
    user_week_data = []
    user_month_data = []
    user_year_data = []
    user_today_data = []
    
    # Usuarios por semana
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        user_count = User.query.filter(func.date(User.fecha_registro) == date).count()
        day_name = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][date.weekday()]
        user_week_data.append({"label": day_name, "value": user_count})
    
    # Usuarios por mes (semanas)
    for week in range(4):
        start_day = min(week * 7 + 1, days_in_month)
        end_day = min((week + 1) * 7, days_in_month)
        
        start_date = first_day.replace(day=start_day)
        end_date = first_day.replace(day=end_day)
        
        user_count = User.query.filter(
            func.date(User.fecha_registro) >= start_date,
            func.date(User.fecha_registro) <= end_date
        ).count()
        
        user_month_data.append({"label": f"Sem {week+1}", "value": user_count})
    
    # Usuarios por año (meses)
    for month in range(1, 13):
        start_date = datetime(current_year, month, 1).date()
        if month == 12:
            end_date = datetime(current_year, month, 31).date()
        else:
            end_date = datetime(current_year, month + 1, 1).date() - timedelta(days=1)
        
        user_count = User.query.filter(
            func.date(User.fecha_registro) >= start_date,
            func.date(User.fecha_registro) <= end_date
        ).count()
        
        month_name = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"][month-1]
        user_year_data.append({"label": month_name, "value": user_count})
    
    # Usuarios por hora (HOY)
    for hour in range(24):
        hour_start = today_start + timedelta(hours=hour)
        hour_end = hour_start + timedelta(hours=1)
        
        utc_offset = timedelta(hours=5)
        utc_hour_start = hour_start + utc_offset
        utc_hour_end = hour_end + utc_offset
        
        user_count = User.query.filter(
            User.fecha_registro >= utc_hour_start,
            User.fecha_registro < utc_hour_end
        ).count()
        
        hour_label = f"{(hour % 12) or 12}:00 {'PM' if hour >= 12 else 'AM'}"
        user_today_data.append({"label": hour_label, "value": user_count})
    
    return {
        "files": {
            "week": week_data,
            "month": month_data,
            "year": year_data,
            "today": today_data
        },
        "users": {
            "week": user_week_data,
            "month": user_month_data,
            "year": user_year_data,
            "today": user_today_data
        }
    }


def get_dashboard_stats(period='month'):
    """Obtiene todas las estadísticas para el dashboard según el período"""
    start_date, end_date = calculate_period_dates(period)
    
    # Estadísticas totales del sistema
    total_users = User.query.count()
    total_clients = User.query.filter_by(rol='cliente').count()
    total_files = Archivo.query.count()
    total_folders = Folder.query.count()
    total_beneficiaries = User.query.filter_by(es_beneficiario=True).count()
    
    # Estadísticas del período
    if start_date and end_date:
        new_users_period = User.query.filter(
            User.fecha_registro >= start_date,
            User.fecha_registro <= end_date
        ).count()
        
        new_clients_period = User.query.filter(
            User.fecha_registro >= start_date,
            User.fecha_registro <= end_date,
            User.rol == 'cliente'
        ).count()
        
        new_files_period = Archivo.query.filter(
            Archivo.fecha_subida >= start_date,
            Archivo.fecha_subida <= end_date
        ).count()
        
        new_folders_period = Folder.query.filter(
            Folder.fecha_creacion >= start_date,
            Folder.fecha_creacion <= end_date
        ).count()
    else:
        # Para 'total', usar todos los datos
        new_users_period = total_users
        new_clients_period = total_clients
        new_files_period = total_files
        new_folders_period = total_folders
    
    return {
        'total_users': total_users,
        'total_clients': total_clients,
        'total_files': total_files,
        'total_folders': total_folders,
        'total_beneficiaries': total_beneficiaries,
        'new_users_period': new_users_period,
        'new_clients_period': new_clients_period,
        'new_files_period': new_files_period,
        'new_folders_period': new_folders_period
    }


def get_recent_files_with_users(limit=10):
    """Obtiene los archivos más recientes con información del usuario"""
    recent_files = db.session.query(Archivo, User).join(
        User, Archivo.usuario_id == User.id
    ).order_by(desc(Archivo.fecha_subida)).limit(limit).all()
    
    return recent_files


def get_recent_activity(limit=10):
    """Obtiene la actividad reciente del sistema"""
    recent_activity = db.session.query(UserActivityLog, User).join(
        User, UserActivityLog.user_id == User.id
    ).order_by(desc(UserActivityLog.fecha)).limit(limit).all()
    
    return recent_activity 