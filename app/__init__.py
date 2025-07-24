import os
from flask import Flask, jsonify, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import config
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from datetime import datetime, timedelta
import logging

# Configurar logging
logger = logging.getLogger(__name__)

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()

login_manager = LoginManager()

def create_app(config_name=None):
    app = Flask(__name__)
    
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    app.config.from_object(config[config_name])
    
    # Inicializar configuración específica del entorno
    if hasattr(config[config_name], 'init_app'):
        config[config_name].init_app(app)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Handler para errores de CSRF
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        logger.error(f"CSRF Error: {e}")
        logger.error(f"CSRF Error description: {e.description}")
        logger.error(f"Request method: {request.method}")
        logger.error(f"Request URL: {request.url}")
        
        # Detectar si es una petición AJAX basándose en headers
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
                  request.headers.get('Content-Type') == 'application/json'
        
        if is_ajax:
            return jsonify({'error': 'CSRF token missing or invalid'}), 400
        else:
            flash('Error de seguridad: Token CSRF faltante o inválido. Por favor, recarga la página e intenta nuevamente.', 'error')
            return redirect(url_for('auth.login'))

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User 
        return User.query.get(int(user_id))

    # Contexto global para CSRF token
    @app.context_processor
    def inject_csrf_token():
        from flask_wtf.csrf import generate_csrf
        return dict(csrf_token=generate_csrf())
    
    # Filtros personalizados de Jinja2
    @app.template_filter('format_colombia_time')
    def format_colombia_time(dt):
        """Convierte una fecha UTC a zona horaria de Colombia (UTC-5)"""
        if dt is None:
            return None
        # Colombia es UTC-5
        colombia_offset = timedelta(hours=5)
        colombia_time = dt - colombia_offset
        return colombia_time

    @app.template_filter('format_date')
    def format_date(dt, format_str='%d/%m/%Y'):
        """Formatea una fecha según el formato especificado"""
        if dt is None:
            return 'No disponible'
        return dt.strftime(format_str)

    @app.template_filter('format_datetime')
    def format_datetime(dt, format_str='%d/%m/%Y %H:%M'):
        """Formatea una fecha y hora según el formato especificado"""
        if dt is None:
            return 'No disponible'
        return dt.strftime(format_str)

    @app.template_filter('role_display')
    def role_display(role):
        """Convierte el rol a un nombre más amigable"""
        role_map = {
            'superadmin': 'Super Administrador',
            'admin': 'Administrador',
            'cliente': 'Cliente',
            'lector': 'Lector'
        }
        return role_map.get(role, role.title())

    @app.template_filter('from_json')
    def from_json(json_string):
        """Convierte una cadena JSON a un objeto Python"""
        import json
        if json_string is None:
            return []
        try:
            return json.loads(json_string)
        except (json.JSONDecodeError, TypeError):
            return []

    from .routes.auth import bp as auth_bp
    from .routes.main import bp as main_bp
    from .routes.users import bp as users_bp
    from .routes.folders import bp as folders_bp
    from .routes.web_register import bp as web_register_bp
    from .routes.listar_dropbox import bp as listar_dropbox_bp, sincronizar_dropbox_a_bd
    from .routes.usuarios import bp as usuarios_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(folders_bp)
    app.register_blueprint(web_register_bp)
    app.register_blueprint(listar_dropbox_bp)
    sincronizar_dropbox_a_bd
    app.register_blueprint(usuarios_bp)

    return app
