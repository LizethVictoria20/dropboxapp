from flask import Blueprint, render_template, request
from werkzeug.security import generate_password_hash
from app import db
from app.models import User
from app.dropbox_utils import create_dropbox_folder

bp = Blueprint("web_register", __name__)

@bp.route("/registro", methods=["GET", "POST"])
def register():
    error = None
    success = None
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if User.query.filter_by(email=email).first():
            error = "Este correo ya está registrado."
        else:
            user = User(email=email, password=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            # Crea carpeta en Dropbox
            path = f"/{email}"
            create_dropbox_folder(path)
            user.dropbox_folder_path = path
            db.session.commit()
            success = "Usuario creado exitosamente."
    return render_template("register.html", error=error, success=success)
