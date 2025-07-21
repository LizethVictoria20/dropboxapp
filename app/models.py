from flask_login import UserMixin
from . import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre = db.Column(db.String(120), nullable=True)
    apellido = db.Column(db.String(120), nullable=True)
    telefono = db.Column(db.String(20), nullable=True)
    ciudad = db.Column(db.String(64), nullable=True)
    estado = db.Column(db.String(64), nullable=True)
    direccion = db.Column(db.String(255), nullable=True)
    codigo_postal = db.Column(db.String(20), nullable=True)
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_acceso = db.Column(db.DateTime, nullable=True)
    activo = db.Column(db.Boolean, default=True)
    dropbox_folder_path = db.Column(db.String, nullable=True)
    es_beneficiario = db.Column(db.Boolean, default=False)
    titular_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    rol = db.Column(db.String(20), nullable=False, default='cliente')
    nacionality = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    lector_extra_permissions = db.Column(db.Text, nullable=True)  # Permisos adicionales para lectores
    
    # Relaciones
    beneficiarios = db.relationship('User', backref=db.backref('titular', remote_side=[id]), lazy=True)
    
    @property
    def username(self):
        """Propiedad para compatibilidad con el template"""
        return self.nombre or self.email.split('@')[0]
    
    @property
    def name(self):
        """Propiedad para compatibilidad con el template"""
        return self.nombre
    
    @property
    def lastname(self):
        """Propiedad para compatibilidad con el template"""
        return self.apellido
    
    @property
    def phone(self):
        """Propiedad para compatibilidad con el template"""
        return self.telefono
    
    @property
    def city(self):
        """Propiedad para compatibilidad con el template"""
        return self.ciudad
    
    @property
    def state(self):
        """Propiedad para compatibilidad con el template"""
        return self.estado
    
    @property
    def address(self):
        """Propiedad para compatibilidad con el template"""
        return self.direccion
    
    @property
    def zip_code(self):
        """Propiedad para compatibilidad con el template"""
        return self.codigo_postal
    
    @property
    def nationality(self):
        """Propiedad para compatibilidad con el template"""
        return self.nacionality
    
    @property
    def date_of_birth(self):
        """Propiedad para compatibilidad con el template"""
        return self.fecha_nacimiento
    
    @property
    def created_at(self):
        """Propiedad para compatibilidad con el template"""
        return self.fecha_registro
    
    @property
    def nombre_completo(self):
        """Devuelve el nombre completo del usuario"""
        if self.nombre and self.apellido:
            return f"{self.nombre} {self.apellido}"
        elif self.nombre:
            return self.nombre
        else:
            return self.email.split('@')[0]
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    # Métodos helper para verificación de roles
    def es_superadmin(self):
        return self.rol == 'superadmin'
    
    def es_admin(self):
        return self.rol == 'admin'
    
    def es_cliente(self):
        return self.rol == 'cliente'
    
    def es_lector(self):
        return self.rol == 'lector'
    
    def tiene_rol(self, rol):
        return self.rol == rol
    
    def puede_administrar(self):
        """Verifica si el usuario puede realizar tareas administrativas"""
        return self.rol in ['admin', 'superadmin']
        
    def registrar_actividad(self, accion, descripcion=None):
        """Registra una actividad del usuario"""
        from flask import request
        
        actividad = UserActivityLog(
            user_id=self.id,
            accion=accion,
            descripcion=descripcion,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent') if request else None
        )
        db.session.add(actividad)
        
        # Actualizar último acceso
        self.ultimo_acceso = datetime.utcnow()
        db.session.commit()

class Beneficiario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    lastname = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(120), nullable=False)
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    titular_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    dropbox_folder_path = db.Column(db.String, nullable=True)
    nationality = db.Column(db.String(100), nullable=True)
    
    titular = db.relationship('User', backref=db.backref('beneficiarios_ben', lazy=True))

    @property
    def name(self):
        """Propiedad para compatibilidad con el template"""
        return self.nombre
    
    @property
    def birth_date(self):
        """Propiedad para compatibilidad con el template"""
        return self.fecha_nacimiento

    def __repr__(self):
        return f"<Beneficiario {self.nombre} ({self.email}) de titular {self.titular_id}>"

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    dropbox_path = db.Column(db.String, nullable=True)
    es_publica = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relación con usuario
    usuario = db.relationship('User', backref=db.backref('folders', lazy=True))

class FolderPermiso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    folder_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    puede_ver = db.Column(db.Boolean, default=True)
    fecha_asignacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    folder = db.relationship('Folder', backref=db.backref('permisos', lazy=True))
    usuario = db.relationship('User', backref=db.backref('permisos_carpetas', lazy=True))

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

    def __repr__(self):
        return f"<Archivo {self.nombre} en {self.dropbox_path}>"

class UserActivityLog(db.Model):
    """Modelo para registrar actividades de usuarios"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    accion = db.Column(db.String(100), nullable=False)  # login, logout, upload, create_folder, etc.
    descripcion = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)  # Para IPv4 e IPv6
    user_agent = db.Column(db.String(255), nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relación con usuario
    usuario = db.relationship('User', backref=db.backref('actividades', lazy=True))
    
    def __repr__(self):
        return f"<ActivityLog {self.accion} by user {self.user_id} at {self.fecha}>"

class Notification(db.Model):
    """Modelo para notificaciones de usuarios"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    titulo = db.Column(db.String(200), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(50), nullable=False, default='info')  # info, success, warning, error
    leida = db.Column(db.Boolean, default=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_leida = db.Column(db.DateTime, nullable=True)
    
    # Relación con usuario
    usuario = db.relationship('User', backref=db.backref('notificaciones', lazy=True))
    
    def marcar_como_leida(self):
        """Marca la notificación como leída"""
        self.leida = True
        self.fecha_leida = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f"<Notification {self.titulo} for user {self.user_id}>"

class SystemSettings(db.Model):
    """Modelo para configuraciones del sistema"""
    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(100), unique=True, nullable=False)
    valor = db.Column(db.Text, nullable=True)
    descripcion = db.Column(db.String(255), nullable=True)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<SystemSettings {self.clave}>"
