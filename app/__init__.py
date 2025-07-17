from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import Config
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()

login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User 
        return User.query.get(int(user_id))

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
