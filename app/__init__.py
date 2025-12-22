import os
from dotenv import load_dotenv
from flask import Flask, jsonify, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import config
from flask_login import LoginManager
from datetime import datetime, timedelta
import logging

# Configurar logging
logger = logging.getLogger(__name__)

# Nota: No inicializamos el gestor de tokens aquí para evitar que falle
# si las variables de entorno aún no se han cargado. Se hará dentro de create_app.

db = SQLAlchemy()
migrate = Migrate()

login_manager = LoginManager()

def create_app(config_name=None):
    app = Flask(__name__)
    
    # Cargar variables de entorno desde .env si existe
    try:
        load_dotenv()
    except Exception:
        pass
    
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    app.config.from_object(config[config_name])
    
    # Inicializar configuración específica del entorno
    if hasattr(config[config_name], 'init_app'):
        config[config_name].init_app(app)
    
    # Deshabilitar CSRF completamente
    app.config['WTF_CSRF_ENABLED'] = False
    
    # Inicializar extensiones
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    
    email_backend = (os.environ.get('EMAIL_BACKEND') or 'smtp').strip().lower()
    logger.info(f"📧 Email backend: {email_backend}")

    # Inicializar Flask-Mail si está disponible (solo necesario para backend SMTP)
    if email_backend != 'sendgrid':
        try:
            from flask_mail import Mail
            # Verificar que la configuración de email esté presente
            if app.config.get('MAIL_SERVER') and app.config.get('MAIL_USERNAME') and app.config.get('MAIL_PASSWORD'):
                mail = Mail(app)
                app.extensions['mail'] = mail
                logger.info("✅ Flask-Mail inicializado correctamente")
            else:
                logger.warning("⚠️ Flask-Mail disponible pero configuración incompleta. Configura MAIL_SERVER, MAIL_USERNAME y MAIL_PASSWORD en .env")
        except ImportError:
            # Flask-Mail no está instalado, continuar sin él
            logger.warning("⚠️ Flask-Mail no está instalado. Instala con: pip install Flask-Mail")
    
    # Configurar login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor inicia sesión para acceder a esta página.'
    login_manager.login_message_category = 'info'
    
    @login_manager.unauthorized_handler
    def unauthorized():
        """Manejador personalizado para usuarios no autenticados"""
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Para requests AJAX, devolver JSON
            return jsonify({
                'success': False,
                'error': 'Debes iniciar sesión para realizar esta acción',
                'redirect': url_for('auth.login')
            }), 401
        else:
            # Para requests normales, redirigir al login
            return redirect(url_for('auth.login'))
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User 
        return User.query.get(int(user_id))
    
    # Registrar blueprints
    from app.routes import auth, main, folders, listar_dropbox, users, usuarios, web_register, admin, tutoriales
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(folders.bp)
    app.register_blueprint(listar_dropbox.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(usuarios.bp)
    app.register_blueprint(web_register.bp)
    app.register_blueprint(admin.admin_bp)
    app.register_blueprint(tutoriales.bp)
    
    # Configurar eventos de SQLAlchemy
    from app.events import setup_events
    setup_events()

    # Inicializar el gestor de tokens de Dropbox una vez cargada la config
    try:
        from app.dropbox_token_manager import get_token_manager
        _ = get_token_manager()
    except Exception as e:
        print(f"Advertencia: No se pudo inicializar el gestor de tokens de Dropbox: {e}")
    
    # Filtros personalizados de Jinja2
    @app.template_filter('datetime')
    def format_datetime(value, format='%d/%m/%Y %H:%M'):
        if value is None:
            return ""
        return value.strftime(format)
    
    @app.template_filter('date')
    def format_date(value, format='%d/%m/%Y'):
        if value is None:
            return ""
        return value.strftime(format)
    
    @app.template_filter('time')
    def format_time(value, format='%H:%M'):
        if value is None:
            return ""
        return value.strftime(format)
    
    @app.template_filter('filesize')
    def format_filesize(value):
        if value is None:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if value < 1024.0:
                return f"{value:.1f} {unit}"
            value /= 1024.0
        return f"{value:.1f} TB"
    
    @app.template_filter('truncate')
    def truncate_filter(s, length=255, killwords=False, end='...'):
        if len(s) <= length:
            return s
        return s[:length] + end
    
    @app.template_filter('format_colombia_time')
    def format_colombia_time(value):
        """Convierte una fecha UTC a la zona horaria de Colombia (UTC-5)"""
        if value is None:
            return None
        
        from datetime import timedelta
        # Colombia está en UTC-5
        colombia_offset = timedelta(hours=-5)
        return value + colombia_offset
    
    @app.template_filter('from_json')
    def from_json_filter(value):
        """Convierte una cadena JSON a un objeto Python"""
        if value is None or value == '':
            return []
        try:
            import json
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    
    @app.context_processor
    def inject_header_notifications():
        """Inyecta las últimas 5 notificaciones del usuario autenticado para el header."""
        try:
            from flask_login import current_user as cu
            from app.models import Notification
            if cu.is_authenticated:
                try:
                    from app.utils.notification_utils import marcar_notificaciones_archivos_fuera_de_revision_como_leidas
                    marcar_notificaciones_archivos_fuera_de_revision_como_leidas(cu.id)
                except Exception:
                    # Si falla el auto-marcado, no bloquea el render del header
                    pass
                ultimas = Notification.query \
                    .filter_by(user_id=cu.id) \
                    .order_by(Notification.fecha_creacion.desc()) \
                    .limit(5).all()
                unread_count = Notification.query.filter_by(user_id=cu.id, leida=False).count()
            else:
                ultimas = []
                unread_count = 0
        except Exception:
            ultimas = []
            unread_count = 0
        return {'header_notifications': ultimas, 'header_unread_count': unread_count}
    
    return app
