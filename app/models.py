from . import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    dropbox_folder_path = db.Column(db.String, nullable=True)

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    dropbox_path = db.Column(db.String, nullable=True)
from datetime import datetime
from . import db

class Archivo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(255), nullable=False)  # nombre del archivo (ej: documento.pdf)
    categoria = db.Column(db.String(100), nullable=False)  # ej: Personal, Laboral
    subcategoria = db.Column(db.String(100), nullable=False)  # ej: Pasaportes, Contratos
    dropbox_path = db.Column(db.String(500), nullable=False)  # ruta completa en Dropbox
    fecha_subida = db.Column(db.DateTime, default=datetime.utcnow)  # fecha/hora en que se subió el archivo
    tamano = db.Column(db.Integer, nullable=True)  # tamaño del archivo en bytes (opcional)
    extension = db.Column(db.String(20), nullable=True)  # extensión (ej: pdf, jpg)
    descripcion = db.Column(db.String(255), nullable=True)  # descripción opcional del archivo

    # Relación con usuario (opcional, solo si manejas usuarios)
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    usuario = db.relationship('User', backref=db.backref('archivos', lazy=True))

    # ¿Quieres guardar también la versión de Dropbox, etiquetas, o permisos? Puedes agregar más campos.

    def __repr__(self):
        return f"<Archivo {self.nombre} en {self.dropbox_path}>"
