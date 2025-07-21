from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import Config
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, timedelta

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()

login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User 
        return User.query.get(int(user_id))

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
