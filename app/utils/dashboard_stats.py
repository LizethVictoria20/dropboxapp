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
        # Documentos
        'pdf': 'PDF',
        'doc': 'Word',
        'docx': 'Word',
        'xls': 'Excel',
        'xlsx': 'Excel',
        'ppt': 'PowerPoint',
        'pptx': 'PowerPoint',
        'odt': 'OpenDocument',
        'ods': 'OpenDocument',
        'odp': 'OpenDocument',
        
        # Imágenes
        'jpg': 'Imagen JPG',
        'jpeg': 'Imagen JPG',
        'png': 'Imagen PNG',
        'gif': 'Imagen GIF',
        'bmp': 'Imagen BMP',
        'tiff': 'Imagen TIFF',
        'svg': 'Imagen SVG',
        'webp': 'Imagen WebP',
        
        # Texto
        'txt': 'Texto',
        'rtf': 'Texto',
        'md': 'Markdown',
        'csv': 'CSV',
        
        # Comprimidos
        'zip': 'Comprimido',
        'rar': 'Comprimido',
        '7z': 'Comprimido',
        'tar': 'Comprimido',
        'gz': 'Comprimido',
        
        # Video
        'mp4': 'Video',
        'avi': 'Video',
        'mov': 'Video',
        'wmv': 'Video',
        'flv': 'Video',
        'mkv': 'Video',
        'webm': 'Video',
        
        # Audio
        'mp3': 'Audio',
        'wav': 'Audio',
        'aac': 'Audio',
        'ogg': 'Audio',
        'flac': 'Audio',
        
        # Código
        'json': 'JSON',
        'xml': 'XML',
        'html': 'HTML',
        'css': 'CSS',
        'js': 'JavaScript',
        'php': 'PHP',
        'py': 'Python',
        'java': 'Java',
        'cpp': 'C++',
        'c': 'C',
        'sql': 'SQL',
        
        # Otros
        'exe': 'Ejecutable',
        'msi': 'Instalador',
        'iso': 'Imagen ISO',
        'log': 'Log',
        'ini': 'Configuración',
        'conf': 'Configuración'
    }
    
    return extension_mapping.get(extension, f'Archivo .{extension.upper()}')


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


def debug_file_extensions():
    """Función de debug para verificar extensiones en la base de datos"""
    from app.models import Archivo
    
    # Obtener todas las extensiones únicas
    extensions = db.session.query(Archivo.extension).distinct().all()
    print("=== DEBUG: Extensiones únicas en la base de datos ===")
    for ext in extensions:
        print(f"Extensión: '{ext[0]}'")
    
    # Contar archivos por extensión
    results = db.session.query(
        Archivo.extension,
        func.count(Archivo.id).label('count')
    ).group_by(Archivo.extension).all()
    
    print("\n=== DEBUG: Conteo por extensión ===")
    total_files = 0
    for extension, count in results:
        print(f"'{extension}': {count} archivos")
        total_files += count
    
    print(f"\nTotal de archivos: {total_files}")
    return results

def get_file_types_stats(start_date=None, end_date=None):
    """Obtiene estadísticas de tipos de archivo para el período especificado"""
    from app.models import Archivo
    
    # Obtener todos los archivos del período
    query = Archivo.query
    
    if start_date and end_date:
        query = query.filter(
            Archivo.fecha_subida >= start_date,
            Archivo.fecha_subida <= end_date
        )
    
    archivos = query.all()
    
    # Contar extensiones extraídas de nombres
    extension_counts = {}
    for archivo in archivos:
        # Intentar obtener extensión del campo extension primero
        extension = archivo.extension
        
        # Si no hay extensión, extraerla del nombre del archivo
        if not extension and '.' in archivo.nombre:
            extension = archivo.nombre.split('.')[-1].lower()
        elif not extension:
            extension = 'sin_extension'
        
        extension_counts[extension] = extension_counts.get(extension, 0) + 1
    
    total_count = sum(extension_counts.values())
    
    # Si no hay archivos, devolver lista con mensaje de "Sin datos"
    if total_count == 0:
        return [{
            'name': 'Sin datos para este período',
            'extension': 'no_data',
            'friendly_name': 'Sin datos',
            'count': 0,
            'percentage': 100.0,
            'color': '#9CA3AF'
        }]
    
    # Colores personalizados para los tipos de archivo
    colors = [
        '#3a6fb5', '#4c7ebd', '#5a8ac7', '#6495ED', '#779ECB', 
        '#89CFF0', '#9BCDED', '#ADD8E6', '#10B981', '#F59E0B', 
        '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4'
    ]
    
    stats = []
    for i, (extension, count) in enumerate(extension_counts.items()):
        # Manejar extensiones nulas o vacías
        if extension == 'sin_extension':
            friendly_name = "Sin extensión"
            display_name = "Sin extensión"
        else:
            friendly_name = get_friendly_file_type(extension)
            # Crear nombre que incluya tanto la extensión como el nombre amigable
            if extension.lower() != friendly_name.lower():
                display_name = f"{friendly_name} (.{extension.lower()})"
            else:
                display_name = friendly_name
        
        # Calcular porcentaje exacto
        percentage = (count / total_count) * 100
        
        stats.append({
            'name': display_name,
            'extension': extension,
            'friendly_name': friendly_name,
            'count': count,
            'percentage': round(percentage, 1),
            'color': colors[i % len(colors)]
        })
    
    # Ordenar por cantidad descendente
    stats.sort(key=lambda x: x['count'], reverse=True)
    
    # Ajustar porcentajes para que sumen exactamente 100%
    if stats:
        # Calcular porcentajes sin redondear primero
        total_count = sum(stat['count'] for stat in stats)
        for stat in stats:
            stat['percentage'] = (stat['count'] / total_count) * 100
        
        # Redondear todos excepto el último
        for i in range(len(stats) - 1):
            stats[i]['percentage'] = round(stats[i]['percentage'], 1)
        
        # Calcular el último porcentaje para que sume exactamente 100%
        total_rounded = sum(stat['percentage'] for stat in stats[:-1])
        stats[-1]['percentage'] = round(100 - total_rounded, 1)
    
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
    total_beneficiaries = Beneficiario.query.count()
    
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
        
        new_beneficiaries_period = Beneficiario.query.filter(
            Beneficiario.fecha_creacion >= start_date,
            Beneficiario.fecha_creacion <= end_date
        ).count()
    else:
        # Para 'total', usar todos los datos
        new_users_period = total_users
        new_clients_period = total_clients
        new_files_period = total_files
        new_folders_period = total_folders
        new_beneficiaries_period = total_beneficiaries
    
    return {
        'total_users': total_users,
        'total_clients': total_clients,
        'total_files': total_files,
        'total_folders': total_folders,
        'total_beneficiaries': total_beneficiaries,
        'new_users_period': new_users_period,
        'new_clients_period': new_clients_period,
        'new_files_period': new_files_period,
        'new_folders_period': new_folders_period,
        'new_beneficiaries_period': new_beneficiaries_period
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