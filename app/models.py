from flask_login import UserMixin
from . import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    dropbox_folder_path = db.Column(db.String, nullable=True)
    nombre = db.Column(db.String(120), nullable=True)
    es_beneficiario = db.Column(db.Boolean, default=False)
    titular_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    beneficiarios = db.relationship('User', backref=db.backref('titular', remote_side=[id]), lazy=True)
    dropbox_folder_path = db.Column(db.String, nullable=True)
    rol = db.Column(db.String(20), nullable=False, default='cliente')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
                    
class Beneficiario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    titular_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    dropbox_folder_path = db.Column(db.String, nullable=True)
    
    titular = db.relationship('User', backref=db.backref('beneficiarios_ben', lazy=True))

    def __repr__(self):
        return f"<Beneficiario {self.nombre} ({self.email}) de titular {self.titular_id}>"

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    dropbox_path = db.Column(db.String, nullable=True)
    es_publica = db.Column(db.Boolean, default=True)
    
from datetime import datetime
from . import db

class FolderPermiso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    folder_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    puede_ver = db.Column(db.Boolean, default=True)

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
