from typing import Optional
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import DateField, FileField, StringField, PasswordField, SubmitField, TextAreaField, ValidationError, SelectField, BooleanField
from wtforms.validators import DataRequired, Length, Optional, EqualTo, Email, Regexp
from app.models import User

class BaseForm(FlaskForm):
    class Meta:
        csrf = False

class LoginForm(BaseForm):
    username = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class ImportForm(BaseForm):
    archivos = FileField('Archivo', validators=[DataRequired()])
    descripcion = StringField('Descripción')
    etiquetas = StringField('Etiquetas')
    
    
class DeleteForm(BaseForm):
    pass

class GeneralForm(BaseForm):
    pass

class PusherForm(BaseForm):
        message = StringField('Message', validators=[DataRequired()])
        
class NewUser(BaseForm):
    username = StringField('Username', validators=[DataRequired()])
    name = StringField('Name', validators=[DataRequired()])
    lastname = StringField('Lastname', validators=[DataRequired()])
    telephone = StringField('Telephone', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    role = StringField('Role', validators=[DataRequired()])
    submit = SubmitField('Crear usuario')

class ProfileForm(BaseForm):
    nombre = StringField('Nombre', validators=[DataRequired()])
    apellido = StringField('Apellido', validators=[DataRequired()])
    email = StringField('Correo', validators=[DataRequired()])
    telefono = StringField('Teléfono')
    ciudad = StringField('Ciudad', validators=[Optional(), Length(max=64)])
    estado = StringField('Estado/Departamento', validators=[Optional(), Length(max=64)])
    direccion = StringField('Dirección', validators=[Optional(), Length(max=255)])
    codigo_postal = StringField('Código Postal', validators=[Optional(), Length(max=20)])
    fecha_nacimiento = DateField('Fecha de Nacimiento', validators=[Optional()])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[
        Optional(),
        EqualTo('new_password', message='Las contraseñas no coinciden')
    ])
    old_password = PasswordField('Contraseña Actual')
    new_password = PasswordField('Nueva Contraseña')
    submit = SubmitField('Guardar Cambios')
    
    
    def validate_email(self, field):
        if field.data != current_user.email: 
            user_with_email = User.query.filter_by(email=field.data).first()
            if user_with_email and user_with_email.id != current_user.id:
                raise ValidationError('Ese correo electrónico ya está registrado por otro usuario.')

class CreateUserForm(BaseForm):
    name = StringField('Nombre', validators=[DataRequired()])
    lastname = StringField('Apellido', validators=[DataRequired()])
    email = StringField('Correo', validators=[DataRequired(), Email()])
    telephone = StringField('Teléfono', validators=[DataRequired()])
    city = StringField('Ciudad', validators=[Optional(), Length(max=64)])
    state = StringField('Estado/Departamento', validators=[Optional(), Length(max=64)])
    address = StringField('Dirección', validators=[Optional(), Length(max=255)])
    zip_code = StringField('Código Postal', validators=[Optional(), Length(max=20)])
    date_of_birth = DateField('Fecha de Nacimiento', validators=[Optional()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    confirm_password = PasswordField('Repita la contraseña', validators=[DataRequired()])
    
    submit = SubmitField('Crear perfil')

class NewFolderForm(BaseForm):
    name = StringField('Nombre de la carpeta', validators=[DataRequired()])
    description = TextAreaField('Descripción (opcional)')
    
class ClienteRegistrationForm(BaseForm):
    name = StringField(
        'Nombres',
        validators=[
            DataRequired(),
            Length(max=120),
            Regexp(
                r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s'\-]+$",
                message="Los nombres solo pueden contener letras y espacios."
            ),
        ],
    )
    lastname = StringField(
        'Apellidos',
        validators=[
            DataRequired(),
            Length(max=120),
            Regexp(
                r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s'\-]+$",
                message="Los apellidos solo pueden contener letras y espacios."
            ),
        ],
    )
    email = StringField('Correo electrónico', validators=[DataRequired(), Email()])
    telephone = StringField(
        'Teléfono',
        validators=[
            DataRequired(),
            Length(max=20),
            Regexp(
                r"^[0-9+\-\s()]+$",
                message="El teléfono solo puede contener números y los símbolos + - ( ) y espacios."
            ),
        ],
    )
    zip_code = StringField(
        'Código Postal',
        validators=[
            DataRequired(),
            Length(max=20),
            Regexp(
                r"^[0-9A-Za-z\s\-]+$",
                message="El código postal solo puede contener letras, números, espacios y guiones."
            ),
        ],
    )
    city = StringField(
        'Ciudad',
        validators=[
            DataRequired(),
            Length(max=64),
            Regexp(
                r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s'\-]+$",
                message="La ciudad solo puede contener letras y espacios."
            ),
        ],
    )
    state = StringField(
        'Estado',
        validators=[
            DataRequired(),
            Length(max=64),
            Regexp(
                r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s'\-]+$",
                message="El estado solo puede contener letras y espacios."
            ),
        ],
    )
    address = StringField('Dirección', validators=[DataRequired(), Length(max=255)])
    document_type = SelectField('Tipo de documento', validators=[DataRequired()], choices=[
        ('', 'Selecciona un tipo de documento'),
        ('cedula', 'Cédula'),
        ('pasaporte', 'Pasaporte'),
        ('nie', 'NIE'),
        ('dni', 'DNI'),
        ('otro', 'Otro')
    ])
    document_number = StringField(
        'Número de documento',
        validators=[
            DataRequired(),
            Length(max=50),
            Regexp(
                r"^[0-9A-Za-z\-]+$",
                message="El número de documento solo puede contener letras, números y guiones."
            ),
        ],
    )
    nationality = SelectField('Nacionalidad', validators=[DataRequired()], choices=[])
    country = SelectField('País', validators=[DataRequired()], choices=[])
    date_of_birth = DateField('Fecha de nacimiento', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[
        DataRequired(),
        Length(min=8, message='La contraseña debe tener al menos 8 caracteres')
    ])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[
        DataRequired(),
        EqualTo('password', message='Las contraseñas no coinciden')
    ])
    communications = BooleanField('Comunicaciones', validators=[DataRequired()])
    
    def validate_email(self, field):
        user_with_email = User.query.filter_by(email=field.data).first()
        if user_with_email:
            raise ValidationError('Correo electrónico ya está registrado.')

    def validate_telephone(self, field):
        if not field.data:
            return
        telefono = (field.data or '').strip()
        user_with_phone = User.query.filter_by(telefono=telefono).first()
        if user_with_phone:
            raise ValidationError('Número de teléfono ya está registrado.')

    def validate_document_number(self, field):
        if not field.data:
            return
        doc = (field.data or '').strip().upper()
        user_with_doc = User.query.filter_by(document_number=doc).first()
        if user_with_doc:
            raise ValidationError('Número de documento ya está registrado.')

class GeneralForm(BaseForm):
    pass

class BeneficiarioForm(BaseForm):
    nombre = StringField('Nombre', validators=[DataRequired(), Length(max=120)])
    email = StringField('Correo electrónico', validators=[DataRequired(), Email()])
    fecha_nacimiento = DateField('Fecha de nacimiento', validators=[Optional()])
    document_type = SelectField('Tipo de documento', validators=[DataRequired()], choices=[
        ('', 'Selecciona un tipo de documento'),
        ('cedula', 'Cédula'),
        ('pasaporte', 'Pasaporte'),
        ('nie', 'NIE'),
        ('dni', 'DNI'),
        ('otro', 'Otro')
    ])
    document_number = StringField('Número de documento', validators=[DataRequired(), Length(max=50)])
    
    def validate_email(self, field):
        # Validación personalizada si es necesaria
        pass