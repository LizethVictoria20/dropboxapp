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

def ensure_beneficiario_folder_no_commit(beneficiario_id):
    """
    Garantiza que un beneficiario tenga su carpeta en Dropbox (sin commit interno).
    Versión para usar dentro de transacciones existentes.
    
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
        
        # Paso 1: Asegurar que el titular tenga carpeta (sin commit)
        titular_result = ensure_titular_folder_no_commit(titular.id)
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
            # NO hacer commit aquí, se hará en la función principal
            
            logger.info(f"Carpeta del beneficiario preparada: {expected_path}")
            return {
                'success': True,
                'message': 'Carpeta preparada exitosamente',
                'path': expected_path,
                'beneficiario_id': beneficiario_id
            }
            
        except Exception as e:
            logger.error(f"Error creando carpeta del beneficiario: {e}")
            # NO hacer rollback aquí, se manejará en la función principal
            return {
                'success': False,
                'error': f"Error creando carpeta: {str(e)}",
                'beneficiario_id': beneficiario_id
            }
            
    except Exception as e:
        logger.error(f"Error general en ensure_beneficiario_folder_no_commit: {e}")
        return {
            'success': False,
            'error': f"Error general: {str(e)}",
            'beneficiario_id': beneficiario_id
        }

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
            
            # Manejar commit de manera segura
            try:
                db.session.commit()
                logger.info(f"Carpeta del beneficiario creada: {expected_path}")
                return {
                    'success': True,
                    'message': 'Carpeta creada exitosamente',
                    'path': expected_path,
                    'beneficiario_id': beneficiario_id
                }
            except Exception as commit_error:
                # Si el commit falla, intentar rollback de manera segura
                try:
                    db.session.rollback()
                except Exception as rollback_error:
                    logger.warning(f"Error en rollback (esperado si la transacción ya está cerrada): {rollback_error}")
                
                logger.error(f"Error en commit después de crear carpeta: {commit_error}")
                return {
                    'success': False,
                    'error': f"Error guardando carpeta en BD: {str(commit_error)}",
                    'beneficiario_id': beneficiario_id
                }
            
        except Exception as e:
            # Error creando la carpeta en Dropbox
            logger.error(f"Error creando carpeta del beneficiario en Dropbox: {e}")
            return {
                'success': False,
                'error': f"Error creando carpeta en Dropbox: {str(e)}",
                'beneficiario_id': beneficiario_id
            }
            
    except Exception as e:
        logger.error(f"Error general en ensure_beneficiario_folder: {e}")
        return {
            'success': False,
            'error': f"Error general: {str(e)}",
            'beneficiario_id': beneficiario_id
        }

def ensure_titular_folder_no_commit(titular_id):
    """
    Garantiza que un titular tenga su carpeta en Dropbox (sin commit interno).
    Versión para usar dentro de transacciones existentes.
    
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
            # NO hacer commit aquí, se hará en la función principal
            
            logger.info(f"Carpeta del titular preparada: {expected_path}")
            return {
                'success': True,
                'message': 'Carpeta preparada exitosamente',
                'path': expected_path,
                'titular_id': titular_id
            }
            
        except Exception as e:
            logger.error(f"Error creando carpeta del titular: {e}")
            # NO hacer rollback aquí, se manejará en la función principal
            return {
                'success': False,
                'error': f"Error creando carpeta: {str(e)}",
                'titular_id': titular_id
            }
            
    except Exception as e:
        logger.error(f"Error general en ensure_titular_folder_no_commit: {e}")
        return {
            'success': False,
            'error': f"Error general: {str(e)}",
            'titular_id': titular_id
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
            
            # Manejar commit de manera segura
            try:
                db.session.commit()
                logger.info(f"Carpeta del titular creada: {expected_path}")
                return {
                    'success': True,
                    'message': 'Carpeta creada exitosamente',
                    'path': expected_path,
                    'titular_id': titular_id
                }
            except Exception as commit_error:
                # Si el commit falla, intentar rollback de manera segura
                try:
                    db.session.rollback()
                except Exception as rollback_error:
                    logger.warning(f"Error en rollback (esperado si la transacción ya está cerrada): {rollback_error}")
                
                logger.error(f"Error en commit después de crear carpeta del titular: {commit_error}")
                return {
                    'success': False,
                    'error': f"Error guardando carpeta del titular en BD: {str(commit_error)}",
                    'titular_id': titular_id
                }
            
        except Exception as e:
            # Error creando la carpeta en Dropbox
            logger.error(f"Error creando carpeta del titular en Dropbox: {e}")
            return {
                'success': False,
                'error': f"Error creando carpeta en Dropbox: {str(e)}",
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

def create_beneficiario_simple(nombre, email, fecha_nacimiento, titular_id):
    """
    Crea un beneficiario de manera simple sin manejo complejo de carpetas.
    Esta función evita completamente los conflictos de transacciones.
    
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
        
        logger.info(f"Beneficiario creado exitosamente: {beneficiario.nombre} (ID: {beneficiario.id})")
        
        # Intentar crear carpeta de manera asíncrona (sin bloquear)
        try:
            # Crear carpeta en Dropbox sin actualizar la BD inmediatamente
            titular = User.query.get(titular_id)
            if titular and titular.dropbox_folder_path:
                expected_path = f"{titular.dropbox_folder_path}/{beneficiario.nombre}_{beneficiario.id}"
                create_dropbox_folder(expected_path)
                
                # Actualizar la BD en una nueva transacción
                try:
                    beneficiario.dropbox_folder_path = expected_path
                    db.session.commit()
                    logger.info(f"Carpeta del beneficiario creada: {expected_path}")
                except Exception as update_error:
                    logger.warning(f"Error actualizando carpeta en BD: {update_error}")
                    # No es crítico, la carpeta ya existe en Dropbox
                
                return {
                    'success': True,
                    'message': f"Beneficiario '{beneficiario.nombre}' creado exitosamente",
                    'beneficiario_id': beneficiario.id,
                    'folder_path': expected_path
                }
            else:
                logger.warning(f"Titular no tiene carpeta configurada: {titular_id}")
                return {
                    'success': True,
                    'message': f"Beneficiario '{beneficiario.nombre}' creado exitosamente",
                    'beneficiario_id': beneficiario.id,
                    'folder_path': None,
                    'warning': 'Titular no tiene carpeta configurada'
                }
                
        except Exception as folder_error:
            logger.warning(f"Error creando carpeta para beneficiario {beneficiario.id}: {folder_error}")
            return {
                'success': True,
                'message': f"Beneficiario '{beneficiario.nombre}' creado exitosamente",
                'beneficiario_id': beneficiario.id,
                'folder_path': None,
                'warning': f"Error creando carpeta: {str(folder_error)}"
            }
            
    except Exception as e:
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.warning(f"Error en rollback: {rollback_error}")
        
        logger.error(f"Error creando beneficiario: {e}")
        return {
            'success': False,
            'error': f"Error creando beneficiario: {str(e)}",
            'beneficiario_id': None
        }

def ensure_beneficiario_folder_new_session(beneficiario_id):
    """
    Garantiza que un beneficiario tenga su carpeta en Dropbox usando una nueva sesión.
    Esta función evita conflictos de transacciones.
    
    Args:
        beneficiario_id: ID del beneficiario
        
    Returns:
        dict: Resultado de la operación
    """
    try:
        # Buscar el beneficiario en una nueva sesión
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
        
        # Paso 1: Asegurar que el titular tenga carpeta (sin commit interno)
        titular_result = ensure_titular_folder_no_commit(titular.id)
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
            
            # Commit de manera segura
            db.session.commit()
            logger.info(f"Carpeta del beneficiario creada: {expected_path}")
            return {
                'success': True,
                'message': 'Carpeta creada exitosamente',
                'path': expected_path,
                'beneficiario_id': beneficiario_id
            }
            
        except Exception as e:
            # Error creando la carpeta en Dropbox
            logger.error(f"Error creando carpeta del beneficiario en Dropbox: {e}")
            try:
                db.session.rollback()
            except Exception as rollback_error:
                logger.warning(f"Error en rollback: {rollback_error}")
            
            return {
                'success': False,
                'error': f"Error creando carpeta en Dropbox: {str(e)}",
                'beneficiario_id': beneficiario_id
            }
            
    except Exception as e:
        logger.error(f"Error general en ensure_beneficiario_folder_new_session: {e}")
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.warning(f"Error en rollback: {rollback_error}")
        
        return {
            'success': False,
            'error': f"Error general: {str(e)}",
            'beneficiario_id': beneficiario_id
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