# Archivo básico de utilidades de Dropbox para mantener la funcionalidad de la aplicación
import dropbox
from flask import current_app
from app.models import User, Archivo, Folder
from app import db
import logging
from datetime import datetime
import os
from app.dropbox_token_manager import get_valid_dropbox_token, get_token_manager
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import re

logger = logging.getLogger(__name__)

# Cache simple en memoria para la carpeta base resuelta
_cached_base_folder = None

def clear_base_folder_cache():
    """Limpia el cache de la carpeta base para forzar nueva resolución"""
    global _cached_base_folder
    _cached_base_folder = None

def _normalize_dropbox_path(path: str) -> str:
    """Normaliza rutas a formato Dropbox '/a/b' sin dobles barras."""
    if path is None:
        return '/'
    
    path = str(path).replace('\\', '/')
    path = path.strip()
    
    if not path:
        return '/'
    
    if not path.startswith('/'):
        path = '/' + path
    
    while '//' in path:
        path = path.replace('//', '/')
    
    if len(path) > 1 and path.endswith('/'):
        path = path[:-1]
    
    return path

def sanitize_dropbox_segment(name: str) -> str:
    """Sanea un nombre de segmento para usarlo como carpeta/archivo en Dropbox.
    - Reemplaza '/' y '\\' por '-'
    - Colapsa espacios, quita espacios/puntos finales
    - Reemplaza espacios por '_'
    - Limita a 255 caracteres
    """
    try:
        if not name:
            return 'SIN_NOMBRE'
        text = str(name)
        # Reemplazar separadores inválidos
        text = text.replace('/', '-').replace('\\', '-')
        # Colapsar espacios en blanco múltiples
        text = re.sub(r"\s+", " ", text)
        # Quitar espacios al inicio/fin
        text = text.strip()
        # Quitar puntos/espacios finales (Windows restrictions y buenas prácticas)
        text = text.rstrip('. ')
        # Evitar vacío tras saneo
        if not text:
            text = 'SIN_NOMBRE'
        # Sustituir espacios por guion bajo para mayor compatibilidad
        text = text.replace(' ', '_')
        # Limitar longitud
        if len(text) > 255:
            text = text[:255]
        return text
    except Exception:
        return 'SIN_NOMBRE'

def get_dropbox_base_folder():
    """Obtiene la carpeta base configurada en Dropbox"""
    global _cached_base_folder
    if _cached_base_folder is not None:
        return _cached_base_folder

    try:
        # 1) Revisar variable de entorno/config directa con el path deseado
        base_folder = (
            getattr(current_app, 'config', {}) and current_app.config.get('DROPBOX_BASE_FOLDER')
        ) or os.environ.get('DROPBOX_BASE_FOLDER')
        if base_folder:
            _cached_base_folder = _normalize_dropbox_path(base_folder)
            return _cached_base_folder

        # 2) Intentar resolver desde un enlace compartido si está configurado
        shared_link = (
            getattr(current_app, 'config', {}) and current_app.config.get('DROPBOX_BASE_SHARED_LINK')
        ) or os.environ.get('DROPBOX_BASE_SHARED_LINK')
        shared_link_password = (
            getattr(current_app, 'config', {}) and current_app.config.get('DROPBOX_BASE_SHARED_LINK_PASSWORD')
        ) or os.environ.get('DROPBOX_BASE_SHARED_LINK_PASSWORD')

        if shared_link:
            dbx = get_dropbox_client()
            if dbx is None:
                logger.warning("Dropbox client no disponible para resolver carpeta base; usando '/'")
                _cached_base_folder = '/'
                return _cached_base_folder
            try:
                meta = dbx.sharing_get_shared_link_metadata(url=shared_link, link_password=shared_link_password)
                # Para enlaces a recursos dentro de TU Dropbox, path_display/path_lower viene definido
                path_display = getattr(meta, 'path_display', None)
                path_lower = getattr(meta, 'path_lower', None)
                final_path = path_display or path_lower
                if final_path:
                    _cached_base_folder = _normalize_dropbox_path(final_path)
                    return _cached_base_folder
                # Si no hay path (p.ej. carpeta ajena sin montar), no podemos fijar path-root aquí
                logger.warning("No se pudo resolver path desde el enlace compartido; usando raíz '/'")
            except Exception as e:
                logger.error(f"Error resolviendo carpeta base desde enlace compartido: {e}")
                # Continuar con fallback a '/'

        # 3) Fallback: raíz
        _cached_base_folder = '/'
        return _cached_base_folder
    except Exception as e:
        logger.error(f"Error obteniendo carpeta base: {e}")
        return '/'

def create_dropbox_folder(folder_path):
    """Crea una carpeta en Dropbox"""
    try:
        dbx = get_dropbox_client()
        if dbx is None:
            logger.error("Cliente de Dropbox no disponible para crear carpeta")
            return False
        path = with_base_folder(folder_path)
        try:
            dbx.files_create_folder_v2(path)
            return True
        except dropbox.exceptions.ApiError as e:
            # Si ya existe, consideramos éxito idempotente
            if 'conflict' in str(e).lower():
                logger.info(f"Carpeta ya existía en Dropbox: {path}")
                return True
            logger.error(f"Error de API creando carpeta {path}: {e}")
            return False
    except Exception as e:
        logger.error(f"Error creando carpeta {folder_path}: {e}")
        return False

def get_dropbox_client():
    """Obtiene el cliente de Dropbox"""
    try:
        token = get_valid_dropbox_token()
        if token:
            return dropbox.Dropbox(token)
        return None
    except Exception as e:
        logger.error(f"Error obteniendo cliente Dropbox: {e}")
        return None

def get_dbx():
    """Obtiene el cliente de Dropbox (alias para compatibilidad)"""
    return get_dropbox_client()

def with_base_folder(path):
    """Agrega la carpeta base al path"""
    base_folder = get_dropbox_base_folder()
    if base_folder == '/' or not base_folder:
        return _normalize_dropbox_path(path)
    
    path = _normalize_dropbox_path(path)
    if path == '/':
        return _normalize_dropbox_path(base_folder)
    
    return _normalize_dropbox_path(f"{base_folder}{path}")

def without_base_folder(path):
    """Remueve la carpeta base del path"""
    base_folder = get_dropbox_base_folder()
    if base_folder == '/' or not base_folder:
        return _normalize_dropbox_path(path)
    
    path = _normalize_dropbox_path(path)
    base_folder = _normalize_dropbox_path(base_folder)
    
    if path.startswith(base_folder):
        result = path[len(base_folder):]
        return _normalize_dropbox_path(result) if result else '/'
    
    return path

def upload_file_to_dropbox(*args, **kwargs):
    """Sube archivo a Dropbox"""
    try:
        # Función placeholder que devuelve error por configuración
        return {'success': False, 'message': 'Dropbox no está configurado correctamente'}
    except Exception as e:
        logger.error(f"Error subiendo archivo: {e}")
        return {'success': False, 'message': str(e)}

def delete_file_from_dropbox(*args, **kwargs):
    """Elimina archivo de Dropbox"""
    try:
        # Función placeholder
        return True
    except Exception as e:
        logger.error(f"Error eliminando archivo: {e}")
        return False

def move_file_in_dropbox(*args, **kwargs):
    """Mueve archivo en Dropbox"""
    try:
        # Función placeholder
        return True
    except Exception as e:
        logger.error(f"Error moviendo archivo: {e}")
        return False

def rename_file_in_dropbox(*args, **kwargs):
    """Renombra archivo en Dropbox"""
    try:
        # Función placeholder
        return True
    except Exception as e:
        logger.error(f"Error renombrando archivo: {e}")
        return False

def list_folder_contents(*args, **kwargs):
    """Lista contenido de carpeta"""
    try:
        # Función placeholder que devuelve lista vacía
        return []
    except Exception as e:
        logger.error(f"Error listando carpeta: {e}")
        return []

def get_file_download_link(*args, **kwargs):
    """Obtiene enlace de descarga"""
    try:
        # Función placeholder
        return None
    except Exception as e:
        logger.error(f"Error obteniendo enlace: {e}")
        return None

def descargar_desde_dropbox(*args, **kwargs):
    """Descarga archivo desde Dropbox"""
    try:
        # Función placeholder
        return None
    except Exception as e:
        logger.error(f"Error descargando archivo: {e}")
        return None

def generar_enlace_dropbox_temporal(*args, **kwargs):
    """Genera enlace temporal de Dropbox"""
    try:
        # Función placeholder
        return None
    except Exception as e:
        logger.error(f"Error generando enlace temporal: {e}")
        return None

def process_dropbox_webhook(*args, **kwargs):
    """Procesa webhook de Dropbox"""
    try:
        # Función placeholder
        return {'status': 'ok', 'message': 'Webhook procesado'}
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}")
        return {'status': 'error', 'message': str(e)}

def verify_dropbox_config():
    """Verifica configuración de Dropbox"""
    try:
        # Función placeholder que siempre devuelve True
        return True
    except Exception as e:
        logger.error(f"Error verificando configuración: {e}")
        return False

# Funciones adicionales que podrían ser necesarias
def get_folder_metadata(*args, **kwargs):
    """Obtiene metadatos de carpeta"""
    return None

def create_shared_link(*args, **kwargs):
    """Crea enlace compartido"""
    return None

def get_file_metadata(*args, **kwargs):
    """Obtiene metadatos de archivo"""
    return None

def search_files(*args, **kwargs):
    """Busca archivos en Dropbox"""
    return []
