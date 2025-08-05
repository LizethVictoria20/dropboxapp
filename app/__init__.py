import os
from flask import Flask, jsonify, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import config
from flask_login import LoginManager
from datetime import datetime, timedelta
import logging

# Configurar logging
logger = logging.getLogger(__name__)

# Inicializar el gestor de tokens de Dropbox al importar la aplicación
try:
    from app.dropbox_token_manager import get_token_manager
    # Inicializar el token manager al arrancar la aplicación
    token_manager = get_token_manager()
except Exception as e:
    print(f"Advertencia: No se pudo inicializar el gestor de tokens de Dropbox: {e}")

db = SQLAlchemy()
migrate = Migrate()

login_manager = LoginManager()

def create_app(config_name=None):
    app = Flask(__name__)
    
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
            flash('Por favor inicia sesión para acceder a esta página.', 'info')
            return redirect(url_for('auth.login'))
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User 
        return User.query.get(int(user_id))
    
    # Registrar blueprints
    from app.routes import auth, main, folders, listar_dropbox, users, usuarios, web_register, admin
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(folders.bp)
    app.register_blueprint(listar_dropbox.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(usuarios.bp)
    app.register_blueprint(web_register.bp)
    app.register_blueprint(admin.admin_bp)
    
    # Configurar eventos de SQLAlchemy
    from app.events import setup_events
    setup_events()
    
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
    
    return app
