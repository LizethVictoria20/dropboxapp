from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from werkzeug.security import generate_password_hash
from datetime import datetime
from app import db
from app.models import User
from app.dropbox_utils import create_dropbox_folder

bp = Blueprint("web_register", __name__)

@bp.route("/registro", methods=["GET", "POST"])
def register():
    # Si el usuario ya está autenticado, redirigir al dashboard
    if current_user.is_authenticated:
        flash('Ya tienes una cuenta activa. Si necesitas crear otra cuenta, cierra sesión primero.', 'info')
        if current_user.rol == 'cliente':
            return redirect(url_for('listar_dropbox.subir_archivo'))
        else:
            return redirect(url_for('main.dashboard'))
    
    error = None
    success = None
    if request.method == "POST":
        email = (request.form.get("email") or '').strip().lower()
        password = request.form.get("password")
        
        if not email or not password:
            error = "Email y contraseña son requeridos."
        else:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                error = "Este correo ya está registrado. Si ya tienes una cuenta, inicia sesión en lugar de registrarte nuevamente."
                flash('Este correo electrónico ya está registrado. Por favor, inicia sesión si ya tienes una cuenta.', 'error')
            else:
                try:
                    user = User(
                        email=email,
                        password_hash=generate_password_hash(password),
                        rol='cliente',
                        activo=True,
                        fecha_registro=datetime.utcnow(),
                    )
                    db.session.add(user)
                    db.session.commit()
                    # Crea carpeta en Dropbox
                    path = f"/{email}"
                    ok = create_dropbox_folder(path)
                    if not ok:
                        raise RuntimeError('No se pudo crear la carpeta en Dropbox. Revisa token y carpeta base.')
                    user.dropbox_folder_path = path
                    db.session.commit()
                    success = "Usuario creado exitosamente."
                    flash('Usuario creado exitosamente. Por favor, inicia sesión.', 'success')
                    return redirect(url_for('auth.login'))
                except Exception as e:
                    db.session.rollback()
                    error = f"Error al crear la cuenta: {str(e)}"
                    flash(f"Error al crear la cuenta: {str(e)}", 'error')
    return render_template("register.html", error=error, success=success)
