# routes/usuarios.py

from flask import Blueprint, render_template, request
from app.models import User, Folder  # Ajusta según tu proyecto
from sqlalchemy import or_

bp = Blueprint('usuarios', __name__)

@bp.route('/usuarios')
def lista_usuarios():
    # Parámetros de búsqueda y paginación
    rol = request.args.get('rol', 'cliente')  # 'cliente' por default
    q = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))

    # Query base filtrando por rol
    query = User.query.filter(User.rol == rol)

    # Si hay búsqueda, filtra por nombre/email/rol
    if q:
        query = query.filter(or_(
            User.nombre.ilike(f"%{q}%"),
            User.email.ilike(f"%{q}%"),
            User.rol.ilike(f"%{q}%"),
        ))

    # Paginación
    pagination = query.order_by(User.nombre).paginate(page=page, per_page=per_page, error_out=False)
    usuarios = pagination.items

    # Carpetas por usuario (solo cuenta, para el badge)
    carpetas_por_usuario = {
        u.id: Folder.query.filter_by(user_id=u.id).count() for u in usuarios
    }

    return render_template(
        "lista_usuarios.html",
        usuarios=usuarios,
        carpetas_por_usuario=carpetas_por_usuario,
        pagination=pagination,
        rol=rol,
        q=q,
    )
