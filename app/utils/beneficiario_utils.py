"""
Utilidades para manejo robusto de beneficiarios y sus carpetas en Dropbox
"""

import logging
from flask import current_app
from app import db
from app.models import User, Beneficiario
from app.dropbox_utils import create_dropbox_folder
import dropbox

logger = logging.getLogger(__name__)

def ensure_beneficiario_folder(beneficiario_id):
    """
    Garantiza que un beneficiario tenga su carpeta en Dropbox.
    Si no existe, la crea. Si existe pero no está en la BD, la actualiza.
    
    Args:
        beneficiario_id: ID del beneficiario
        
    Returns:
        dict: Resultado de la operación
    """
    try:
        # Buscar el beneficiario
        beneficiario = Beneficiario.query.get(beneficiario_id)
        if not beneficiario:
            return {
                'success': False,
                'error': 'Beneficiario no encontrado',
                'beneficiario_id': beneficiario_id
            }
        
        # Verificar que tenga titular
        if not beneficiario.titular:
            return {
                'success': False,
                'error': 'Beneficiario no tiene titular asociado',
                'beneficiario_id': beneficiario_id
            }
        
        titular = beneficiario.titular
        
        # Paso 1: Asegurar que el titular tenga carpeta
        titular_result = ensure_titular_folder(titular.id)
        if not titular_result['success']:
            return {
                'success': False,
                'error': f"Error con carpeta del titular: {titular_result['error']}",
                'beneficiario_id': beneficiario_id
            }
        
        # Paso 2: Crear carpeta del beneficiario
        expected_path = f"{titular.dropbox_folder_path}/{beneficiario.nombre}_{beneficiario.id}"
        
        # Verificar si ya tiene carpeta configurada
        if beneficiario.dropbox_folder_path:
            # Verificar que la carpeta existe en Dropbox
            if verify_folder_exists(beneficiario.dropbox_folder_path):
                logger.info(f"Carpeta del beneficiario ya existe: {beneficiario.dropbox_folder_path}")
                return {
                    'success': True,
                    'message': 'Carpeta ya existe',
                    'path': beneficiario.dropbox_folder_path,
                    'beneficiario_id': beneficiario_id
                }
            else:
                # La carpeta no existe en Dropbox, recrearla
                logger.warning(f"Carpeta configurada no existe en Dropbox: {beneficiario.dropbox_folder_path}")
        
        # Crear la carpeta
        try:
            create_dropbox_folder(expected_path)
            beneficiario.dropbox_folder_path = expected_path
            db.session.commit()
            
            logger.info(f"Carpeta del beneficiario creada: {expected_path}")
            return {
                'success': True,
                'message': 'Carpeta creada exitosamente',
                'path': expected_path,
                'beneficiario_id': beneficiario_id
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando carpeta del beneficiario: {e}")
            return {
                'success': False,
                'error': f"Error creando carpeta: {str(e)}",
                'beneficiario_id': beneficiario_id
            }
            
    except Exception as e:
        logger.error(f"Error general en ensure_beneficiario_folder: {e}")
        return {
            'success': False,
            'error': f"Error general: {str(e)}",
            'beneficiario_id': beneficiario_id
        }

def ensure_titular_folder(titular_id):
    """
    Garantiza que un titular tenga su carpeta en Dropbox.
    
    Args:
        titular_id: ID del titular
        
    Returns:
        dict: Resultado de la operación
    """
    try:
        titular = User.query.get(titular_id)
        if not titular:
            return {
                'success': False,
                'error': 'Titular no encontrado',
                'titular_id': titular_id
            }
        
        # Verificar si ya tiene carpeta configurada
        if titular.dropbox_folder_path:
            # Verificar que la carpeta existe en Dropbox
            if verify_folder_exists(titular.dropbox_folder_path):
                logger.info(f"Carpeta del titular ya existe: {titular.dropbox_folder_path}")
                return {
                    'success': True,
                    'message': 'Carpeta ya existe',
                    'path': titular.dropbox_folder_path,
                    'titular_id': titular_id
                }
        
        # Crear carpeta del titular
        expected_path = f"/{titular.email}"
        try:
            create_dropbox_folder(expected_path)
            titular.dropbox_folder_path = expected_path
            db.session.commit()
            
            logger.info(f"Carpeta del titular creada: {expected_path}")
            return {
                'success': True,
                'message': 'Carpeta creada exitosamente',
                'path': expected_path,
                'titular_id': titular_id
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando carpeta del titular: {e}")
            return {
                'success': False,
                'error': f"Error creando carpeta: {str(e)}",
                'titular_id': titular_id
            }
            
    except Exception as e:
        logger.error(f"Error general en ensure_titular_folder: {e}")
        return {
            'success': False,
            'error': f"Error general: {str(e)}",
            'titular_id': titular_id
        }

def verify_folder_exists(folder_path):
    """
    Verifica si una carpeta existe en Dropbox.
    
    Args:
        folder_path: Ruta de la carpeta en Dropbox
        
    Returns:
        bool: True si existe, False si no
    """
    try:
        api_key = current_app.config.get("DROPBOX_API_KEY")
        if not api_key:
            logger.error("DROPBOX_API_KEY no configurada")
            return False
        
        dbx = dropbox.Dropbox(api_key)
        metadata = dbx.files_get_metadata(folder_path)
        return True
    except dropbox.exceptions.ApiError as e:
        if "not_found" in str(e):
            return False
        else:
            logger.error(f"Error verificando carpeta {folder_path}: {e}")
            return False
    except Exception as e:
        logger.error(f"Error general verificando carpeta {folder_path}: {e}")
        return False

def create_beneficiario_with_folder(nombre, email, fecha_nacimiento, titular_id):
    """
    Crea un beneficiario y garantiza que tenga su carpeta en Dropbox.
    
    Args:
        nombre: Nombre del beneficiario
        email: Email del beneficiario
        fecha_nacimiento: Fecha de nacimiento
        titular_id: ID del titular
        
    Returns:
        dict: Resultado de la operación
    """
    try:
        # Crear el beneficiario
        beneficiario = Beneficiario(
            nombre=nombre,
            email=email,
            fecha_nacimiento=fecha_nacimiento,
            titular_id=titular_id
        )
        
        db.session.add(beneficiario)
        db.session.commit()
        
        # Garantizar que tenga carpeta
        folder_result = ensure_beneficiario_folder(beneficiario.id)
        
        if folder_result['success']:
            logger.info(f"Beneficiario creado exitosamente: {beneficiario.nombre}")
            return {
                'success': True,
                'message': 'Beneficiario creado con carpeta',
                'beneficiario_id': beneficiario.id,
                'folder_path': folder_result['path']
            }
        else:
            # Si falla la creación de carpeta, eliminar el beneficiario
            db.session.delete(beneficiario)
            db.session.commit()
            
            logger.error(f"Error creando carpeta, beneficiario eliminado: {folder_result['error']}")
            return {
                'success': False,
                'error': f"Error creando carpeta: {folder_result['error']}",
                'beneficiario_id': None
            }
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando beneficiario: {e}")
        return {
            'success': False,
            'error': f"Error general: {str(e)}",
            'beneficiario_id': None
        }

def fix_all_beneficiarios():
    """
    Corrige todos los beneficiarios que no tienen carpetas.
    
    Returns:
        dict: Resumen de la operación
    """
    try:
        beneficiarios = Beneficiario.query.all()
        fixed_count = 0
        error_count = 0
        errors = []
        
        for beneficiario in beneficiarios:
            result = ensure_beneficiario_folder(beneficiario.id)
            if result['success']:
                fixed_count += 1
            else:
                error_count += 1
                errors.append({
                    'beneficiario': f"{beneficiario.nombre} ({beneficiario.email})",
                    'error': result['error']
                })
        
        return {
            'success': True,
            'total': len(beneficiarios),
            'fixed': fixed_count,
            'errors': error_count,
            'error_details': errors
        }
        
    except Exception as e:
        logger.error(f"Error en fix_all_beneficiarios: {e}")
        return {
            'success': False,
            'error': f"Error general: {str(e)}"
        } 