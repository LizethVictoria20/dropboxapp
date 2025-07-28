import dropbox
from flask import current_app
from app.models import User, Archivo, Folder
from app import db
import logging

logger = logging.getLogger(__name__)

def get_dbx():
    api_key = current_app.config["DROPBOX_API_KEY"]
    return dropbox.Dropbox(api_key)

def sync_user_files_from_webhook(account_id, cursor=None):
    """
    Sincroniza archivos de un usuario específico basado en notificaciones de webhook
    
    Args:
        account_id: ID de la cuenta de Dropbox
        cursor: Cursor para continuar desde donde se quedó
    """
    try:
        dbx = get_dbx()
        
        # Buscar usuario por account_id (asumiendo que tienes este campo)
        # Si no tienes account_id, puedes usar el email o crear un mapeo
        user = User.query.filter_by(dropbox_account_id=account_id).first()
        
        if not user:
            logger.warning(f"Usuario no encontrado para account_id: {account_id}")
            return
        
        # Obtener cambios desde el cursor
        if cursor:
            result = dbx.files_list_folder_continue(cursor)
        else:
            result = dbx.files_list_folder(user.dropbox_folder_path, recursive=True)
        
        # Procesar cambios
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                # Es un archivo
                sync_file_to_database(entry, user)
            elif isinstance(entry, dropbox.files.FolderMetadata):
                # Es una carpeta
                sync_folder_to_database(entry, user)
        
        # Guardar el cursor para la próxima sincronización
        if hasattr(result, 'cursor'):
            user.dropbox_cursor = result.cursor
            db.session.commit()
        
        logger.info(f"Sincronización completada para usuario: {user.email}")
        
    except Exception as e:
        logger.error(f"Error sincronizando archivos para account_id {account_id}: {e}")
        raise

def sync_file_to_database(file_metadata, user):
    """
    Sincroniza un archivo específico a la base de datos
    
    Args:
        file_metadata: Metadata del archivo de Dropbox
        user: Usuario propietario del archivo
    """
    try:
        # Verificar si el archivo ya existe en la base de datos
        existing_file = Archivo.query.filter_by(dropbox_path=file_metadata.path_display).first()
        
        if existing_file:
            # Actualizar archivo existente
            existing_file.nombre = file_metadata.name
            existing_file.tamaño = file_metadata.size
            existing_file.fecha_modificacion = file_metadata.server_modified
            logger.info(f"Archivo actualizado: {file_metadata.name}")
        else:
            # Crear nuevo archivo
            # Extraer categoría y subcategoría del path
            path_parts = file_metadata.path_display.strip('/').split('/')
            
            categoria = "Sin categoría"
            subcategoria = "Sin subcategoría"
            
            if len(path_parts) > 2:
                categoria = path_parts[1]
                subcategoria = path_parts[2]
            elif len(path_parts) > 1:
                categoria = path_parts[1]
            
            new_file = Archivo(
                nombre=file_metadata.name,
                categoria=categoria,
                subcategoria=subcategoria,
                dropbox_path=file_metadata.path_display,
                usuario_id=user.id,
                tamaño=file_metadata.size,
                fecha_subida=file_metadata.server_modified,
                fecha_modificacion=file_metadata.server_modified
            )
            db.session.add(new_file)
            logger.info(f"Nuevo archivo agregado: {file_metadata.name}")
        
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error sincronizando archivo {file_metadata.name}: {e}")
        db.session.rollback()

def sync_folder_to_database(folder_metadata, user):
    """
    Sincroniza una carpeta específica a la base de datos
    
    Args:
        folder_metadata: Metadata de la carpeta de Dropbox
        user: Usuario propietario de la carpeta
    """
    try:
        # Verificar si la carpeta ya existe en la base de datos
        existing_folder = Folder.query.filter_by(dropbox_path=folder_metadata.path_display).first()
        
        if not existing_folder:
            # Crear nueva carpeta
            new_folder = Folder(
                name=folder_metadata.name,
                user_id=user.id,
                dropbox_path=folder_metadata.path_display,
                es_publica=True  # Por defecto las carpetas son públicas
            )
            db.session.add(new_folder)
            logger.info(f"Nueva carpeta agregada: {folder_metadata.name}")
            db.session.commit()
        
    except Exception as e:
        logger.error(f"Error sincronizando carpeta {folder_metadata.name}: {e}")
        db.session.rollback()

def process_dropbox_webhook(data):
    """
    Procesa los datos de un webhook de Dropbox
    
    Args:
        data: Datos JSON del webhook
    """
    try:
        # Verificar estructura del webhook
        if 'list_folder' not in data:
            logger.error("Estructura de webhook inválida")
            return False
        
        accounts = data.get('list_folder', {}).get('accounts', {})
        
        for account_id, account_data in accounts.items():
            logger.info(f"Procesando cambios para cuenta: {account_id}")
            
            # Sincronizar archivos para esta cuenta
            sync_user_files_from_webhook(account_id)
        
        return True
        
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}")
        return False

def create_dropbox_folder(path):
    """Crea una carpeta en Dropbox"""
    dbx = get_dbx()
    try:
        dbx.files_create_folder_v2(path)
    except dropbox.exceptions.ApiError as e:
        if "conflict" not in str(e):
            raise e

def move_dropbox_item(from_path, to_path):
    """Mueve un elemento en Dropbox"""
    dbx = get_dbx()
    dbx.files_move_v2(from_path, to_path)

def rename_dropbox_item(from_path, new_name):
    """Renombra un elemento en Dropbox"""
    to_path = '/'.join(from_path.split('/')[:-1] + [new_name])
    move_dropbox_item(from_path, to_path)
