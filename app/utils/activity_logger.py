"""
Utilidades para registrar actividades de usuarios en el sistema
"""
from flask import request
from ..models import UserActivityLog, db
from datetime import datetime

def log_user_activity(user_id, accion, descripcion=None, ip_address=None, user_agent=None):
    """
    Registra una actividad del usuario en la base de datos
    
    Args:
        user_id (int): ID del usuario
        accion (str): Tipo de acción (login, upload_file, etc.)
        descripcion (str, optional): Descripción detallada de la actividad
        ip_address (str, optional): Dirección IP del usuario
        user_agent (str, optional): User agent del navegador
    """
    try:
        # Si no se proporciona IP, intentar obtenerla de la request
        if ip_address is None and request:
            ip_address = request.remote_addr
        
        # Si no se proporciona user agent, intentar obtenerlo de la request
        if user_agent is None and request:
            user_agent = request.headers.get('User-Agent', '')
        
        # Crear el registro de actividad
        activity = UserActivityLog(
            user_id=user_id,
            accion=accion,
            descripcion=descripcion,
            ip_address=ip_address,
            user_agent=user_agent,
            fecha=datetime.utcnow()
        )
        
        # Guardar en la base de datos
        db.session.add(activity)
        db.session.commit()
        
        return True
        
    except Exception as e:
        # En caso de error, hacer rollback y registrar el error
        db.session.rollback()
        print(f"Error al registrar actividad: {str(e)}")
        return False

def log_login(user_id, ip_address=None, user_agent=None):
    """Registra un inicio de sesión"""
    return log_user_activity(
        user_id=user_id,
        accion='login',
        descripcion='Usuario inició sesión en el sistema',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_logout(user_id, ip_address=None, user_agent=None):
    """Registra un cierre de sesión"""
    return log_user_activity(
        user_id=user_id,
        accion='logout',
        descripcion='Usuario cerró sesión en el sistema',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_file_upload(user_id, filename, ip_address=None, user_agent=None):
    """Registra la subida de un archivo"""
    return log_user_activity(
        user_id=user_id,
        accion='upload_file',
        descripcion=f'Usuario subió el archivo: {filename}',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_file_delete(user_id, filename, ip_address=None, user_agent=None):
    """Registra la eliminación de un archivo"""
    return log_user_activity(
        user_id=user_id,
        accion='delete_file',
        descripcion=f'Usuario eliminó el archivo: {filename}',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_file_rename(user_id, old_name, new_name, ip_address=None, user_agent=None):
    """Registra el renombrado de un archivo"""
    return log_user_activity(
        user_id=user_id,
        accion='rename_file',
        descripcion=f'Usuario renombró el archivo de "{old_name}" a "{new_name}"',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_file_move(user_id, filename, old_path, new_path, ip_address=None, user_agent=None):
    """Registra el movimiento de un archivo"""
    return log_user_activity(
        user_id=user_id,
        accion='move_file',
        descripcion=f'Usuario movió el archivo "{filename}" de "{old_path}" a "{new_path}"',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_profile_update(user_id, fields_updated=None, ip_address=None, user_agent=None):
    """Registra la actualización del perfil"""
    descripcion = 'Usuario actualizó su perfil'
    if fields_updated:
        descripcion += f' - Campos modificados: {", ".join(fields_updated)}'
    
    return log_user_activity(
        user_id=user_id,
        accion='update_profile',
        descripcion=descripcion,
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_beneficiary_add(user_id, beneficiary_name, ip_address=None, user_agent=None):
    """Registra la adición de un beneficiario"""
    return log_user_activity(
        user_id=user_id,
        accion='add_beneficiary',
        descripcion=f'Usuario agregó beneficiario: {beneficiary_name}',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_beneficiary_remove(user_id, beneficiary_name, ip_address=None, user_agent=None):
    """Registra la eliminación de un beneficiario"""
    return log_user_activity(
        user_id=user_id,
        accion='remove_beneficiary',
        descripcion=f'Usuario eliminó beneficiario: {beneficiary_name}',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_permission_change(user_id, permissions_changed, ip_address=None, user_agent=None):
    """Registra cambios en permisos"""
    return log_user_activity(
        user_id=user_id,
        accion='change_permissions',
        descripcion=f'Se modificaron permisos: {permissions_changed}',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_folder_create(user_id, folder_name, ip_address=None, user_agent=None):
    """Registra la creación de una carpeta"""
    return log_user_activity(
        user_id=user_id,
        accion='create_folder',
        descripcion=f'Usuario creó la carpeta: {folder_name}',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_folder_delete(user_id, folder_name, ip_address=None, user_agent=None):
    """Registra la eliminación de una carpeta"""
    return log_user_activity(
        user_id=user_id,
        accion='delete_folder',
        descripcion=f'Usuario eliminó la carpeta: {folder_name}',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_user_activation(user_id, activated_by_id, ip_address=None, user_agent=None):
    """Registra la activación de un usuario"""
    return log_user_activity(
        user_id=user_id,
        accion='activate_user',
        descripcion=f'Usuario activado por administrador (ID: {activated_by_id})',
        ip_address=ip_address,
        user_agent=user_agent
    )

def log_user_deactivation(user_id, deactivated_by_id, ip_address=None, user_agent=None):
    """Registra la desactivación de un usuario"""
    return log_user_activity(
        user_id=user_id,
        accion='deactivate_user',
        descripcion=f'Usuario desactivado por administrador (ID: {deactivated_by_id})',
        ip_address=ip_address,
        user_agent=user_agent
    ) 