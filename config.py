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
    # (Opcional) Enlace compartido si se quiere resolver namespace desde un link
    # Nota: Si se configura, la app resolverá el path real del folder a partir del shared link
    # y TODAS las operaciones (crear/listar/subir/mover/descargar) quedarán contenidas allí.
    # Requiere que el token configurado tenga acceso a esa carpeta (idealmente es tu Dropbox).
    # IMPORTANTE: No hardcodear un shared link aquí.
    # Si se define, se debe hacer únicamente por variable de entorno.
    DROPBOX_BASE_SHARED_LINK = os.environ.get('DROPBOX_BASE_SHARED_LINK')
    # (Opcional) Contraseña del enlace compartido, si el link está protegido
    DROPBOX_BASE_SHARED_LINK_PASSWORD = os.environ.get('DROPBOX_BASE_SHARED_LINK_PASSWORD')

    # Subcarpeta del proyecto dentro de la carpeta base.
    # Si está vacía, NO se agrega ninguna subcarpeta adicional.
    DROPBOX_PROJECT_SUBFOLDER = os.environ.get('DROPBOX_PROJECT_SUBFOLDER') or ''
    
    # Configuración de logging
    LOG_LEVEL = 'INFO'
    
    # Configuración de Email (Flask-Mail)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
    MAIL_TIMEOUT = int(os.environ.get('MAIL_TIMEOUT', 10))
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    # Gmail App Password suele copiarse con espacios (XXXX XXXX XXXX XXXX).
    # Normalizamos quitando espacios para evitar fallos de autenticación.
    MAIL_PASSWORD = (os.environ.get('MAIL_PASSWORD') or '').replace(' ', '') or None
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', os.environ.get('MAIL_USERNAME'))
    
    # Configuración de Twilio (SMS y WhatsApp)
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')  # Formato: whatsapp:+14155238886
    TWILIO_DEFAULT_COUNTRY_CODE = os.environ.get('TWILIO_DEFAULT_COUNTRY_CODE', '+1')
    
    # URL de la aplicación para enlaces en notificaciones
    # Nota: si APP_URL existe pero está vacío, usar fallback.
    APP_URL = os.environ.get('APP_URL') or 'http://localhost:5000'
    
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
