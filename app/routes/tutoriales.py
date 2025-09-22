from flask import Blueprint, render_template

bp = Blueprint('tutoriales', __name__, url_prefix='/tutoriales')


@bp.route('/')
def index():
    """Página principal con opciones de tutoriales disponibles"""
    return render_template('tutoriales_index.html')


@bp.route('/registro')
def registro():
    """Tutorial paso a paso para registrarse en la plataforma Mi Caso"""
    return render_template('tutorial_registro.html')


@bp.route('/cargar-documentos')
def cargar_documentos():
    """Tutorial paso a paso para cargar documentos y evidencias"""
    return render_template('tutorial_documentos.html')


@bp.route('/solucionar-problemas')
def solucionar_problemas():
    """Tutorial paso a paso para solucionar problemas en la plataforma"""
    return render_template('tutorial_problemas.html')
