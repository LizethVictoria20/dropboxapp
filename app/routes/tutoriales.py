from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint('tutoriales', __name__, url_prefix='/tutoriales')


@bp.route('/')
@login_required
def index():
    """Página principal de tutoriales e información"""
    return render_template('tutoriales.html')
