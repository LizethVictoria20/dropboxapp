import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "cambiaesto")
    # Usar ruta absoluta para SQLite
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'mydropboxapp.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DROPBOX_API_KEY = os.environ.get("DROPBOX_API_KEY", "")
