from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import Config

db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    from .routes.auth import bp as auth_bp
    from .routes.users import bp as users_bp
    from .routes.folders import bp as folders_bp
    from .routes.web_register import bp as web_register_bp
    from .routes.listar_dropbox import bp as listar_dropbox_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(folders_bp)
    app.register_blueprint(web_register_bp)
    app.register_blueprint(listar_dropbox_bp)

    return app
