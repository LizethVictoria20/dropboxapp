import dropbox
from flask import current_app
from app.models import User, Archivo, Folder
from app import db
import logging
from datetime import datetime
import os

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

def verify_dropbox_config():
    """
    Verifica que la configuración de Dropbox esté disponible y funcional
    
    Returns:
        dict: Estado de la configuración con detalles
    """
    config_status = {
        'api_key': {
            'available': bool(current_app.config.get('DROPBOX_API_KEY')),
            'value': current_app.config.get('DROPBOX_API_KEY', 'No configurado')[:10] + '...' if current_app.config.get('DROPBOX_API_KEY') else 'No configurado'
        },
        'app_key': {
            'available': bool(current_app.config.get('DROPBOX_APP_KEY')),
            'value': current_app.config.get('DROPBOX_APP_KEY', 'No configurado')
        },
        'app_secret': {
            'available': bool(current_app.config.get('DROPBOX_APP_SECRET')),
            'value': 'Configurado' if current_app.config.get('DROPBOX_APP_SECRET') else 'No configurado'
        },
        'access_token': {
            'available': bool(current_app.config.get('DROPBOX_ACCESS_TOKEN')),
            'value': 'Configurado' if current_app.config.get('DROPBOX_ACCESS_TOKEN') else 'No configurado'
        }
    }
    
    # Verificar si al menos la API_KEY está configurada
    api_key_available = config_status['api_key']['available']
    
    # Intentar conectar a Dropbox si hay API_KEY
    connection_status = {
        'connected': False,
        'error': None,
        'account_info': None
    }
    
    if api_key_available:
        try:
            dbx = get_dbx()
            account = dbx.users_get_current_account()
            connection_status['connected'] = True
            connection_status['account_info'] = {
                'email': account.email,
                'name': account.name.display_name,
                'country': account.country
            }
            logger.info(f"Conectado a Dropbox como: {account.email}")
        except Exception as e:
            connection_status['connected'] = False
            connection_status['error'] = str(e)
            logger.error(f"Error conectando a Dropbox: {e}")
    
    return {
        'config': config_status,
        'connection': connection_status,
        'all_configured': all(status['available'] for status in config_status.values()),
        'api_key_configured': api_key_available
    }

def get_dropbox_client():
    """
    Obtiene un cliente de Dropbox configurado
    
    Returns:
        dropbox.Dropbox: Cliente de Dropbox configurado
        
    Raises:
        ValueError: Si la configuración no está disponible
    """
    config_status = verify_dropbox_config()
    
    if not config_status['api_key_configured']:
        raise ValueError("DROPBOX_API_KEY no está configurado. Verifica las variables de entorno.")
    
    if not config_status['connection']['connected']:
        raise ValueError(f"No se pudo conectar a Dropbox: {config_status['connection']['error']}")
    
    return get_dbx()

def descargar_desde_dropbox(path):
    path = os.path.normpath(path).replace("\\", "/")
    try:
        dbx = get_dbx()
        metadata, response = dbx.files_download(path)
        return response.content
    except dropbox.exceptions.ApiError as e:
        logger.error(f"Error descargando archivo {path}: {e}")
        
        # Manejar errores específicos de Dropbox
        if "not_found" in str(e):
            raise Exception(f"El archivo no existe en Dropbox: {path}")
        elif "insufficient_scope" in str(e):
            raise Exception(f"No tienes permisos para acceder al archivo: {path}")
        elif "invalid_access_token" in str(e):
            raise Exception("Token de acceso de Dropbox inválido o expirado")
        elif "rate_limit" in str(e):
            raise Exception("Límite de velocidad excedido. Intenta de nuevo en unos minutos")
        else:
            raise Exception(f"Error de Dropbox: {str(e)}")
    except Exception as e:
        logger.error(f"Error inesperado descargando archivo {path}: {e}")
        raise Exception(f"Error inesperado al descargar el archivo: {e}")

def generar_enlace_dropbox_temporal(path, duracion_horas=4):
    try:
        dbx = get_dbx()
        
        # Crear enlace temporal sin configuración de expiración específica
        # Dropbox manejará la expiración automáticamente
        shared_link = dbx.sharing_create_shared_link(path)
        
        # Convertir a enlace directo de descarga
        direct_link = shared_link.url.replace('www.dropbox.com', 'dl.dropboxusercontent.com')
        
        logger.info(f"Enlace temporal generado para {path}: {direct_link}")
        return direct_link
        
    except dropbox.exceptions.ApiError as e:
        logger.error(f"Error generando enlace temporal para {path}: {e}")
        
        # Manejar errores específicos de Dropbox
        if "shared_link_already_exists" in str(e):
            # Si el enlace ya existe, intentar obtenerlo
            try:
                shared_links = dbx.sharing_list_shared_links(path)
                if shared_links.links:
                    direct_link = shared_links.links[0].url.replace('www.dropbox.com', 'dl.dropboxusercontent.com')
                    logger.info(f"Enlace existente recuperado para {path}: {direct_link}")
                    return direct_link
            except Exception as get_error:
                logger.error(f"Error obteniendo enlace existente para {path}: {get_error}")
        
        raise Exception(f"No se pudo generar el enlace temporal: {e}")
    except Exception as e:
        logger.error(f"Error inesperado generando enlace temporal para {path}: {e}")
        raise Exception(f"Error inesperado al generar el enlace temporal: {e}")
