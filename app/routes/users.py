from flask import Blueprint, redirect, render_template, request, jsonify, current_app, url_for
from app import db
from app.models import Beneficiario, User
from app.dropbox_utils import create_dropbox_folder
from app.routes.listar_dropbox import obtener_estructura_dropbox
import dropbox

bp = Blueprint('users', __name__, url_prefix='/users')

@bp.route('/create', methods=['POST'])
def create_user():
    email = request.json.get('email')
    password = request.json.get('password')
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Usuario ya existe'}), 400

    user = User(email=email, password=password)
    db.session.add(user)
    db.session.commit()

    # Crea carpeta en Dropbox
    path = f"/{email}"
    create_dropbox_folder(path)
    user.dropbox_folder_path = path
    db.session.commit()
    return jsonify({'message': 'Usuario y carpeta creados'}), 201


@bp.route("/crear_beneficiario", methods=["GET", "POST"])
def crear_beneficiario():
    titulares = User.query.filter_by(es_beneficiario=False).all()
    if request.method == "POST":
        nombre = request.form.get("nombre")
        email = request.form.get("email")
        fecha_nac = request.form.get("fecha_nacimiento")
        titular_id = request.form.get("titular_id")
        # Validaciones aquí...

        beneficiario = Beneficiario(
            nombre=nombre,
            email=email,
            fecha_nacimiento=fecha_nac,
            titular_id=titular_id
        )
        db.session.add(beneficiario)
        db.session.commit()
        # Crea carpeta en Dropbox dentro del titular
        titular = User.query.get(titular_id)
        path_ben = f"{titular.dropbox_folder_path}/{nombre}_{beneficiario.id}"
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        dbx.files_create_folder_v2(path_ben)
        beneficiario.dropbox_folder_path = path_ben
        db.session.commit()
        return redirect(url_for("users.crear_beneficiario"))
    return render_template("crear_beneficiario.html", titulares=titulares)


@bp.route("/listar_beneficiarios")
def listar_beneficiarios():
    titulares = User.query.filter_by(es_beneficiario=False).all()
    estructuras_titulares = {}
    estructuras_beneficiarios = {}

    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
    for titular in titulares:
        estructuras_titulares[titular.id] = obtener_estructura_dropbox(path=titular.dropbox_folder_path)
        for ben in titular.beneficiarios:
            estructuras_beneficiarios[ben.id] = obtener_estructura_dropbox(path=ben.dropbox_folder_path)

    return render_template(
        "listar_beneficiarios.html",
        titulares=titulares,
        estructuras_titulares=estructuras_titulares,
        estructuras_beneficiarios=estructuras_beneficiarios
    )
