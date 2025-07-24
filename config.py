import os
import secrets

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    # Usar ruta absoluta para SQLite
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'mydropboxapp.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DROPBOX_API_KEY = os.environ.get("DROPBOX_API_KEY", "")
    WTF_CSRF_ENABLED = True
    
    # Configuración de sesiones para producción
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Configuración CSRF para producción
    WTF_CSRF_SSL_STRICT = False  # Deshabilitar si no usas HTTPS
    WTF_CSRF_TIME_LIMIT = 3600

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_SSL_STRICT = False

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    WTF_CSRF_SSL_STRICT = True
    
    # Asegurar que SECRET_KEY esté configurada en producción
    @classmethod
    def init_app(cls, app):
        if not os.environ.get('SECRET_KEY'):
            raise ValueError("SECRET_KEY debe estar configurada en producción")

# Configuración por defecto basada en FLASK_ENV
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
