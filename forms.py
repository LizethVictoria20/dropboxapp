from typing import Optional
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import DateField, FileField, StringField, PasswordField, SubmitField, TextAreaField, ValidationError, SelectField
from wtforms.validators import DataRequired, Length, Optional, EqualTo, Email
from app.models import User

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class ImportForm(FlaskForm):
    archivos = FileField('Archivo', validators=[DataRequired()])
    descripcion = StringField('Descripción')
    etiquetas = StringField('Etiquetas')
    
    
class DeleteForm(FlaskForm):
    pass

class GeneralForm(FlaskForm):
    pass

class PusherForm(FlaskForm):
        message = StringField('Message', validators=[DataRequired()])
        
class NewUser(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    name = StringField('Name', validators=[DataRequired()])
    lastname = StringField('Lastname', validators=[DataRequired()])
    telephone = StringField('Telephone', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    role = StringField('Role', validators=[DataRequired()])
    submit = SubmitField('Crear usuario')

class ProfileForm(FlaskForm):
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

class CreateUserForm(FlaskForm):
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

class NewFolderForm(FlaskForm):
    name = StringField('Nombre de la carpeta', validators=[DataRequired()])
    description = TextAreaField('Descripción (opcional)')