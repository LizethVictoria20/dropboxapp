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
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User 
        return User.query.get(int(user_id))
    
    # Registrar blueprints
    from app.routes import auth, main, folders, listar_dropbox, users, usuarios, web_register
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(folders.bp)
    app.register_blueprint(listar_dropbox.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(usuarios.bp)
    app.register_blueprint(web_register.bp)
    
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
    
    return app
