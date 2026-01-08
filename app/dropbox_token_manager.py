import os
import requests
import json
import logging
from datetime import datetime, timedelta
from flask import current_app
import threading
import time
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class DropboxTokenManager:
    """
    Gestor de tokens de Dropbox con renovación automática
    """
    
    def __init__(self):
        # Cargar variables desde .env si existe
        try:
            load_dotenv()
        except Exception:
            pass
        
        self.app_key = os.environ.get('DROPBOX_APP_KEY')
        self.app_secret = os.environ.get('DROPBOX_APP_SECRET')
        self.access_token = os.environ.get('DROPBOX_ACCESS_TOKEN')
        self.refresh_token = os.environ.get('DROPBOX_REFRESH_TOKEN')
        # Fallback para compatibilidad con configuración actual
        if not self.access_token:
            self.access_token = os.environ.get('DROPBOX_API_KEY')
        
        self.token_file = Path('.dropbox_tokens.json')
        self.last_refresh = None
        self.refresh_lock = threading.Lock()
        
        # Cargar tokens guardados si existen
        self._load_saved_tokens()
        
        # Iniciar thread de renovación automática solo si hay refresh token
        if self.refresh_token:
            self._start_auto_refresh_thread()
    
    def _load_saved_tokens(self):
        """Carga tokens guardados desde archivo"""
        try:
            if self.token_file.exists():
                with open(self.token_file, 'r') as f:
                    tokens = json.load(f)
                    # No sobrescribir variables ya definidas por entorno;
                    # usar el archivo solo como fallback
                    file_access = tokens.get('access_token')
                    file_refresh = tokens.get('refresh_token')
                    if not self.access_token and file_access:
                        self.access_token = file_access
                    if not self.refresh_token and file_refresh:
                        self.refresh_token = file_refresh
                    self.last_refresh = datetime.fromisoformat(tokens.get('last_refresh', '1970-01-01'))
                    logger.info("Tokens cargados desde archivo")
        except Exception as e:
            logger.error(f"Error cargando tokens guardados: {e}")
    
    def _save_tokens(self):
        """Guarda tokens actualizados en archivo"""
        try:
            tokens = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'last_refresh': datetime.now().isoformat()
            }
            with open(self.token_file, 'w') as f:
                json.dump(tokens, f, indent=2)
            logger.info("Tokens guardados en archivo")
        except Exception as e:
            logger.error(f"Error guardando tokens: {e}")
    
    def refresh_env_view(self):
        """Refresca credenciales desde variables de entorno si están disponibles.
        No borra valores existentes; solo actualiza cuando hay un valor nuevo en el entorno.
        """
        try:
            app_key_env = os.environ.get('DROPBOX_APP_KEY')
            app_secret_env = os.environ.get('DROPBOX_APP_SECRET')
            access_env = os.environ.get('DROPBOX_ACCESS_TOKEN') or os.environ.get('DROPBOX_API_KEY')
            refresh_env = os.environ.get('DROPBOX_REFRESH_TOKEN')
            
            if app_key_env and app_key_env != self.app_key:
                self.app_key = app_key_env
            if app_secret_env and app_secret_env != self.app_secret:
                self.app_secret = app_secret_env
            if access_env and access_env != self.access_token:
                self.access_token = access_env
            if refresh_env and refresh_env != self.refresh_token:
                self.refresh_token = refresh_env
        except Exception as e:
            logger.warning(f"No se pudo refrescar credenciales desde entorno: {e}")
    
    def _update_environment_variables(self):
        """Actualiza las variables de entorno con el nuevo token"""
        try:
            # Actualizar variable de entorno
            os.environ['DROPBOX_ACCESS_TOKEN'] = self.access_token
            if self.refresh_token:
                os.environ['DROPBOX_REFRESH_TOKEN'] = self.refresh_token
            
            # Actualizar configuración de Flask
            if current_app:
                current_app.config['DROPBOX_ACCESS_TOKEN'] = self.access_token
                if self.refresh_token:
                    current_app.config['DROPBOX_REFRESH_TOKEN'] = self.refresh_token
            
            logger.info("Variables de entorno actualizadas con nuevo token")
        except Exception as e:
            logger.error(f"Error actualizando variables de entorno: {e}")
    
    def validate_refresh_token(self):
        """
        Valida si el refresh token es válido haciendo una petición de prueba
        
        Returns:
            dict: {"valid": bool, "error": str|None, "status_code": int|None}
        """
        try:
            if not self.refresh_token:
                return {"valid": False, "error": "No hay refresh token disponible", "status_code": None}
            
            if not self.app_key or not self.app_secret:
                return {"valid": False, "error": "DROPBOX_APP_KEY o DROPBOX_APP_SECRET no configurados", "status_code": None}
            
            # URL para renovar token
            url = "https://api.dropboxapi.com/oauth2/token"
            
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': self.app_key,
                'client_secret': self.app_secret
            }
            
            response = requests.post(url, data=data, timeout=30)
            
            if response.status_code == 200:
                return {"valid": True, "error": None, "status_code": 200}
            else:
                # Intentar identificar causas específicas para mejor diagnóstico
                specific = None
                try:
                    j = response.json()
                    specific = j.get('error') if isinstance(j, dict) else None
                except Exception:
                    specific = None
                if specific == 'app is disabled':
                    error_msg = (
                        "La app de Dropbox está deshabilitada en Developers ('app is disabled'). "
                        "Debes reactivarla o crear una nueva app y regenerar tokens."
                    )
                else:
                    error_msg = f"Refresh token inválido: {response.status_code} - {response.text}"
                return {"valid": False, "error": error_msg, "status_code": response.status_code}
                
        except Exception as e:
            return {"valid": False, "error": f"Error validando refresh token: {e}", "status_code": None}

    def refresh_access_token(self):
        """
        Renueva el token de acceso usando el refresh token
        
        Returns:
            bool: True si la renovación fue exitosa, False en caso contrario
        """
        with self.refresh_lock:
            try:
                # Primero validar que el refresh token sea válido
                validation = self.validate_refresh_token()
                if not validation["valid"]:
                    # Mensajes diferenciados para evitar confusión
                    logger.error(f"Refresh token inválido: {validation['error']}")
                    if validation["status_code"] == 400:
                        err_text = validation.get('error') or ''
                        err_text_l = err_text.lower() if isinstance(err_text, str) else ''
                        if 'app is disabled' in err_text_l or 'deshabilitad' in err_text_l:
                            logger.error(
                                "CRÍTICO: La app de Dropbox está deshabilitada. Reactívala en la consola de Developers "
                                "o crea una nueva app y regenera el refresh token."
                            )
                        else:
                            logger.error(
                                "CRÍTICO: El refresh token está revocado/expirado. Se requiere reautenticación manual."
                            )
                    return False
                
                # URL para renovar token
                url = "https://api.dropboxapi.com/oauth2/token"
                
                data = {
                    'grant_type': 'refresh_token',
                    'refresh_token': self.refresh_token,
                    'client_id': self.app_key,
                    'client_secret': self.app_secret
                }
                
                response = requests.post(url, data=data, timeout=30)
                
                if response.status_code == 200:
                    token_data = response.json()
                    
                    # Actualizar tokens
                    self.access_token = token_data.get('access_token')
                    self.refresh_token = token_data.get('refresh_token', self.refresh_token)
                    self.last_refresh = datetime.now()
                    
                    # Guardar tokens actualizados
                    self._save_tokens()
                    
                    # Actualizar variables de entorno
                    self._update_environment_variables()
                    
                    logger.info("Token de acceso renovado exitosamente")
                    return True
                else:
                    error_msg = f"Error renovando token: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    
                    # Manejar casos específicos de error
                    if response.status_code == 400:
                        try:
                            error_data = response.json()
                            if error_data.get('error') == 'invalid_grant':
                                logger.error(
                                    "CRÍTICO: Refresh token revocado. Regenera tokens manualmente desde Dropbox App Console."
                                )
                            elif error_data.get('error') == 'app is disabled':
                                logger.error(
                                    "CRÍTICO: La app de Dropbox está deshabilitada. Reactívala o crea una nueva app y regenera tokens."
                                )
                        except Exception:
                            pass
                    
                    return False
                    
            except Exception as e:
                logger.error(f"Error inesperado renovando token: {e}")
                return False
    
    def get_token_validation_status(self):
        """
        Obtiene el estado completo de validación de tokens
        
        Returns:
            dict: Estado detallado de tokens
        """
        status = {
            "access_token_configured": bool(self.access_token),
            "refresh_token_configured": bool(self.refresh_token),
            "app_credentials_configured": bool(self.app_key and self.app_secret),
            "refresh_token_valid": False,
            "access_token_valid": False,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "errors": []
        }
        
        # Asegurar que vemos las últimas variables del entorno
        self.refresh_env_view()

        # Validar refresh token si está configurado
        if self.refresh_token:
            validation = self.validate_refresh_token()
            status["refresh_token_valid"] = validation["valid"]
            if not validation["valid"]:
                status["errors"].append(f"Refresh token: {validation['error']}")
        
        # Validar access token usando el flujo normal (incluye refresh on-demand)
        try:
            token = self.get_valid_access_token()
            if token:
                import dropbox
                dbx = dropbox.Dropbox(token)
                dbx.users_get_current_account()
                status["access_token_valid"] = True
            else:
                status["access_token_valid"] = False
                status["errors"].append("Access token: No hay token de acceso disponible")
        except Exception as e:
            status["access_token_valid"] = False
            status["errors"].append(f"Access token: {str(e)}")
        
        return status

    def get_valid_access_token(self):
        """
        Obtiene un token de acceso válido, renovándolo si es necesario
        
        Returns:
            str|None: Token de acceso válido o None si no se puede obtener
        """
        # Asegurar que vemos las últimas variables del entorno
        self.refresh_env_view()

        # Si no hay refresh token, usar el token actual (modo legacy)
        if not self.refresh_token:
            logger.warning("No hay refresh token configurado, usando access token actual")
            return self.access_token
        
        # Primero validar que el refresh token no esté revocado
        validation = self.validate_refresh_token()
        if not validation["valid"]:
            logger.error(f"Refresh token inválido: {validation['error']}")
            # Permitir fallback opcional al access token cuando el refresh token está revocado
            allow_fallback_env = os.environ.get('DROPBOX_ALLOW_ACCESS_TOKEN_FALLBACK', 'true')
            allow_fallback = str(allow_fallback_env).strip().lower() in ("1", "true", "yes", "y")
            if validation["status_code"] == 400:
                logger.error("CRÍTICO: El refresh token está revocado. Se requiere reautenticación manual.")
                if allow_fallback and self.access_token:
                    logger.warning("Usando access token actual como fallback temporal (DROPBOX_ALLOW_ACCESS_TOKEN_FALLBACK habilitado)")
                    return self.access_token
                return None  # No usar token potencialmente inválido sin fallback
            # Para otros errores, intentar usar el token actual
            logger.warning("Error validando refresh token, usando access token actual")
            return self.access_token
        
        def _is_access_token_valid(token: str) -> bool:
            try:
                import dropbox
                dropbox.Dropbox(token).users_get_current_account()
                return True
            except Exception:
                return False

        # Si no tenemos certeza de frescura, refrescar (cada ~50 min por seguridad)
        needs_refresh = (
            self.last_refresh is None or
            datetime.now() - self.last_refresh > timedelta(minutes=50)
        )

        # Si no "toca" refrescar por tiempo, igual validamos el token.
        # Esto cubre el caso típico en local: access token viejo en .env pero refresh token válido.
        if not needs_refresh and self.access_token:
            if _is_access_token_valid(self.access_token):
                return self.access_token
            logger.warning("Access token inválido detectado; forzando refresh...")
            needs_refresh = True

        if needs_refresh:
            logger.info("Renovando token de acceso...")
            if self.refresh_access_token():
                logger.info("Token renovado exitosamente")
                return self.access_token
            logger.error("No se pudo renovar el token")
            return None

        return self.access_token
    
    def _start_auto_refresh_thread(self):
        """Inicia thread para renovación automática cada 45 minutos"""
        def auto_refresh_worker():
            while True:
                try:
                    time.sleep(45 * 60)  # 45 minutos
                    if self.refresh_token:
                        logger.info("Renovación automática de token...")
                        self.refresh_access_token()
                except Exception as e:
                    logger.error(f"Error en renovación automática: {e}")
        
        # Iniciar thread en background
        refresh_thread = threading.Thread(target=auto_refresh_worker, daemon=True)
        refresh_thread.start()
        logger.info("Thread de renovación automática iniciado")
    
    def test_connection(self):
        """
        Prueba la conexión con Dropbox usando el token actual
        
        Returns:
            dict: Estado de la conexión
        """
        try:
            import dropbox
            token = self.get_valid_access_token()
            if not token:
                return {
                    'connected': False,
                    'error': 'No hay token de acceso disponible'
                }
            
            dbx = dropbox.Dropbox(token)
            account = dbx.users_get_current_account()
            
            return {
                'connected': True,
                'account_info': {
                    'email': account.email,
                    'name': account.name.display_name,
                    'country': account.country
                }
            }
        except Exception as e:
            logger.error(f"Error probando conexión: {e}")
            return {
                'connected': False,
                'error': str(e)
            }
    
    def get_token_status(self):
        """
        Obtiene el estado actual de los tokens
        
        Returns:
            dict: Información del estado de los tokens
        """
        return {
            'access_token_configured': bool(self.access_token),
            'refresh_token_configured': bool(self.refresh_token),
            'app_key_configured': bool(self.app_key),
            'app_secret_configured': bool(self.app_secret),
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'next_refresh': (self.last_refresh + timedelta(minutes=45)).isoformat() if self.last_refresh else None
        }

# Instancia global del gestor de tokens
token_manager = None

def get_token_manager():
    """Obtiene la instancia global del gestor de tokens"""
    global token_manager
    if token_manager is None:
        token_manager = DropboxTokenManager()
    return token_manager

def reset_token_manager():
    """Resetea la instancia global del gestor de tokens para releer entorno/archivo."""
    global token_manager
    token_manager = DropboxTokenManager()
    return token_manager

def refresh_dropbox_token():
    """Función para renovar manualmente el token de Dropbox"""
    manager = get_token_manager()
    return manager.refresh_access_token()

def get_valid_dropbox_token():
    """Obtiene un token válido de Dropbox"""
    manager = get_token_manager()
    return manager.get_valid_access_token()

def validate_dropbox_tokens():
    """Valida el estado completo de los tokens de Dropbox"""
    manager = get_token_manager()
    return manager.get_token_validation_status() 