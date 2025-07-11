from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models import User
from app.dropbox_utils import create_dropbox_folder

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
