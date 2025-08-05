import os
import requests
import json
import logging
from datetime import datetime, timedelta
from flask import current_app
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

class DropboxTokenManager:
    """
    Gestor de tokens de Dropbox con renovación automática
    """
    
    def __init__(self):
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
                    self.access_token = tokens.get('access_token', self.access_token)
                    self.refresh_token = tokens.get('refresh_token', self.refresh_token)
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
    
    def refresh_access_token(self):
        """
        Renueva el token de acceso usando el refresh token
        
        Returns:
            bool: True si la renovación fue exitosa, False en caso contrario
        """
        with self.refresh_lock:
            try:
                if not self.refresh_token:
                    logger.error("No hay refresh token disponible")
                    return False
                
                if not self.app_key or not self.app_secret:
                    logger.error("DROPBOX_APP_KEY o DROPBOX_APP_SECRET no configurados")
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
                    logger.error(f"Error renovando token: {response.status_code} - {response.text}")
                    return False
                    
            except Exception as e:
                logger.error(f"Error inesperado renovando token: {e}")
                return False
    
    def get_valid_access_token(self):
        """
        Obtiene un token de acceso válido, renovándolo si es necesario
        
        Returns:
            str: Token de acceso válido
        """
        # Si no hay refresh token, usar el token actual
        if not self.refresh_token:
            return self.access_token
        
        # Verificar si necesitamos renovar (cada 50 minutos para estar seguros)
        if (self.last_refresh is None or 
            datetime.now() - self.last_refresh > timedelta(minutes=50)):
            
            logger.info("Renovando token de acceso...")
            if self.refresh_access_token():
                return self.access_token
            else:
                logger.warning("No se pudo renovar el token, usando el actual")
        
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

def refresh_dropbox_token():
    """Función para renovar manualmente el token de Dropbox"""
    manager = get_token_manager()
    return manager.refresh_access_token()

def get_valid_dropbox_token():
    """Obtiene un token válido de Dropbox"""
    manager = get_token_manager()
    return manager.get_valid_access_token() 