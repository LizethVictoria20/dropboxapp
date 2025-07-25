from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from app import db
from app.models import Folder, User
from app.dropbox_utils import create_dropbox_folder

bp = Blueprint('folders', __name__, url_prefix='/folders')

@bp.route('/create', methods=['POST'])
@login_required
def create_folder():
    user_id = request.json.get('user_id')
    name = request.json.get('name')
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Usuario no encontrado'}), 404

    path = f"{user.dropbox_folder_path}/{name}"
    create_dropbox_folder(path)
    folder = Folder(
        name=name, 
        user_id=user_id, 
        dropbox_path=path,
        es_publica=True  # Por defecto las carpetas son públicas
    )
    db.session.add(folder)
    db.session.commit()
    
    # Registrar actividad
    current_user.registrar_actividad('folder_created', f'Carpeta "{name}" creada')
    
    return jsonify({'message': 'Carpeta creada', 'path': path}), 201
