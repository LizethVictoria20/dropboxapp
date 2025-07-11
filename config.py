import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "cambiaesto")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://usuario:contraseña@localhost/mydropboxapp"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DROPBOX_API_KEY = os.environ.get("DROPBOX_API_KEY", "")
