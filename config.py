import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Deshabilitar CSRF completamente
    WTF_CSRF_ENABLED = False
    
    # Configuración de sesiones
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = False  # Cambiar a True en producción con HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Configuración de archivos - Aumentado a 1GB
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024  # 1GB
    UPLOAD_FOLDER = 'uploads'
    
    # Configuración adicional para archivos grandes
    MAX_CONTENT_PATH = None
    SEND_FILE_MAX_AGE_DEFAULT = 0
    
    # Configuración de Dropbox
    DROPBOX_APP_KEY = os.environ.get('DROPBOX_APP_KEY')
    DROPBOX_APP_SECRET = os.environ.get('DROPBOX_APP_SECRET')
    DROPBOX_ACCESS_TOKEN = os.environ.get('DROPBOX_ACCESS_TOKEN')
    DROPBOX_REFRESH_TOKEN = os.environ.get('DROPBOX_REFRESH_TOKEN')
    DROPBOX_API_KEY = os.environ.get('DROPBOX_API_KEY')
    # Carpeta base global para contener TODAS las operaciones en Dropbox
    DROPBOX_BASE_FOLDER = os.environ.get('DROPBOX_BASE_FOLDER')
    # (Opcional) Enlace compartido si se quiere resolver namespace desde un link
    DROPBOX_BASE_SHARED_LINK = os.environ.get('DROPBOX_BASE_SHARED_LINK')
    
    # Configuración de logging
    LOG_LEVEL = 'INFO'
    
    @staticmethod
    def init_app(app):
        pass

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_TRACK_MODIFICATIONS = True
    LOG_LEVEL = 'DEBUG'
    WTF_CSRF_ENABLED = False

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = True  # Requiere HTTPS
    LOG_LEVEL = 'WARNING'
    WTF_CSRF_ENABLED = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
