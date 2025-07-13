from flask import Blueprint, json, render_template, current_app, request, redirect, url_for, flash
from app.categorias import CATEGORIAS
import dropbox
from app.models import Archivo, User
from app import db

bp = Blueprint("listar_dropbox", __name__)

def obtener_carpetas_dropbox_estructura(path="", dbx=None):
    if dbx is None:
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
    res = dbx.files_list_folder(path, recursive=True)
    all_paths = [entry.path_display for entry in res.entries if isinstance(entry, dropbox.files.FolderMetadata)]

    # Construir el árbol
    tree = {}
    for full_path in all_paths:
        parts = full_path.strip("/").split("/")
        node = tree
        for part in parts:
            node = node.setdefault(part, {})

    return tree

def obtener_estructura_dropbox(path="", dbx=None):
    if dbx is None:
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
    res = dbx.files_list_folder(path, recursive=True)
    estructura = {"_subcarpetas": {}, "_archivos": []}

    for entry in res.entries:
        parts = entry.path_display.strip("/").split("/")
        node = estructura

        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            # Si es carpeta
            if is_last and isinstance(entry, dropbox.files.FolderMetadata):
                node["_subcarpetas"].setdefault(part, {"_subcarpetas": {}, "_archivos": []})
            # Si es archivo
            elif is_last and isinstance(entry, dropbox.files.FileMetadata):
                node["_archivos"].append(part)
            # Si es subcarpeta intermedia
            else:
                node = node["_subcarpetas"].setdefault(part, {"_subcarpetas": {}, "_archivos": []})

    return estructura


@bp.route("/carpetas_dropbox")
def carpetas_dropbox():
    estructuras_usuarios = {}
    usuarios_dict = {u.id: u for u in User.query.all()}
    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])

    for user in usuarios_dict.values():
        if not user.dropbox_folder_path:
            user.dropbox_folder_path = f"/{user.email}"
            try:
                dbx.files_create_folder_v2(user.dropbox_folder_path)
            except dropbox.exceptions.ApiError as e:
                if "conflict" not in str(e):
                    raise e
            db.session.commit()
        path = user.dropbox_folder_path
        estructura = obtener_estructura_dropbox(path=path)
        estructuras_usuarios[user.id] = estructura

    return render_template(
        "carpetas_dropbox.html",
        estructuras_usuarios=estructuras_usuarios,
        usuarios=usuarios_dict,
        estructuras_usuarios_json=json.dumps(estructuras_usuarios)
    )



@bp.route("/crear_carpeta", methods=["POST"])
def crear_carpeta():
    nombre = request.form.get("nombre")
    padre = request.form.get("padre", "")
    if not nombre:
        flash("El nombre de la carpeta es obligatorio.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    # Construir la ruta en Dropbox
    ruta = padre.rstrip("/") + "/" + nombre if padre else "/" + nombre
    try:
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        dbx.files_create_folder_v2(ruta)
        flash(f"Carpeta '{ruta}' creada correctamente.", "success")
    except dropbox.exceptions.ApiError as e:
        flash(f"Error creando carpeta: {e}", "error")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))



@bp.route("/subir_archivo", methods=["GET", "POST"])
def subir_archivo():
    if request.method == "GET":
        usuarios = User.query.all()
        return render_template(
            "subir_archivo.html",
            categorias=CATEGORIAS.keys(),
            categorias_json=json.dumps(CATEGORIAS),
            usuarios=usuarios
        )

    usuario_id = request.form.get("usuario_id")
    usuario = User.query.get(usuario_id)
    if not usuario:
        flash("Selecciona un usuario válido.", "error")
        return redirect(url_for("listar_dropbox.subir_archivo"))

    categoria = request.form.get("categoria")
    subcategoria = request.form.get("subcategoria")
    archivo = request.files.get("archivo")
    if not (categoria and subcategoria and archivo):
        flash("Completa todos los campos", "error")
        return redirect(url_for("listar_dropbox.subir_archivo"))

    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
    # 1. Carpeta raíz de usuario (usa email o dropbox_folder_path)
    if usuario.dropbox_folder_path:
        carpeta_usuario = usuario.dropbox_folder_path
    else:
        carpeta_usuario = f"/{usuario.email}"
        try:
            dbx.files_create_folder_v2(carpeta_usuario)
        except dropbox.exceptions.ApiError as e:
            if "conflict" not in str(e):
                raise e
        usuario.dropbox_folder_path = carpeta_usuario
        db.session.commit()

    # 2. Crear categoría y subcategoría dentro de carpeta usuario
    ruta_categoria = f"{carpeta_usuario}/{categoria}"
    try:
        dbx.files_create_folder_v2(ruta_categoria)
    except dropbox.exceptions.ApiError as e:
        if "conflict" not in str(e):
            raise e
    ruta_subcat = f"{ruta_categoria}/{subcategoria}"
    try:
        dbx.files_create_folder_v2(ruta_subcat)
    except dropbox.exceptions.ApiError as e:
        if "conflict" not in str(e):
            raise e

    # 3. Subir archivo a esa ruta
    dropbox_dest = f"{ruta_subcat}/{archivo.filename}"
    dbx.files_upload(archivo.read(), dropbox_dest, mode=dropbox.files.WriteMode("overwrite"))

    # 4. Guarda en base de datos
    nuevo_archivo = Archivo(
        nombre=archivo.filename,
        categoria=categoria,
        subcategoria=subcategoria,
        dropbox_path=dropbox_dest,
        usuario_id=usuario.id
    )
    db.session.add(nuevo_archivo)
    db.session.commit()

    flash("Archivo subido y registrado para el usuario seleccionado.", "success")
    return redirect(url_for("listar_dropbox.subir_archivo"))
  
  
  
@bp.route('/mover_archivo/<archivo_nombre>/<path:carpeta_actual>', methods=['GET', 'POST'])
def mover_archivo(archivo_nombre, carpeta_actual):
    from app.models import Archivo, User

    # Busca el archivo en la base de datos usando dropbox_path
    old_dropbox_path = f"{carpeta_actual}/{archivo_nombre}".replace('//', '/')
    archivo = Archivo.query.filter_by(dropbox_path=old_dropbox_path).first()
    if not archivo:
        flash("No se encontró el archivo en la base de datos.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    if request.method == 'GET':
        usuarios = User.query.all()
        categorias = list(CATEGORIAS.keys())
        return render_template(
            "mover_archivo.html",
            archivo=archivo,
            usuarios=usuarios,
            categorias=categorias,
            categorias_json=json.dumps(CATEGORIAS)
        )

    # POST: procesar movimiento
    usuario_id = request.form.get("usuario_id")
    categoria = request.form.get("categoria")
    subcategoria = request.form.get("subcategoria")
    usuario = User.query.get(usuario_id)
    if not usuario:
        flash("Selecciona un usuario válido.", "error")
        return redirect(url_for("listar_dropbox.mover_archivo", archivo_nombre=archivo_nombre, carpeta_actual=carpeta_actual))

    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
    # Crear carpetas destino si no existen
    carpeta_usuario = usuario.dropbox_folder_path or f"/{usuario.email}"
    try:
        dbx.files_create_folder_v2(carpeta_usuario)
    except dropbox.exceptions.ApiError as e:
        if "conflict" not in str(e):
            raise e
    usuario.dropbox_folder_path = carpeta_usuario
    db.session.commit()
    ruta_categoria = f"{carpeta_usuario}/{categoria}"
    try:
        dbx.files_create_folder_v2(ruta_categoria)
    except dropbox.exceptions.ApiError as e:
        if "conflict" not in str(e):
            raise e
    ruta_subcat = f"{ruta_categoria}/{subcategoria}"
    try:
        dbx.files_create_folder_v2(ruta_subcat)
    except dropbox.exceptions.ApiError as e:
        if "conflict" not in str(e):
            raise e

    # Mover archivo en Dropbox
    nuevo_destino = f"{ruta_subcat}/{archivo.nombre}"
    dbx.files_move_v2(archivo.dropbox_path, nuevo_destino, allow_shared_folder=True, autorename=True)

    # Actualiza en BD
    archivo.dropbox_path = nuevo_destino
    archivo.categoria = categoria
    archivo.subcategoria = subcategoria
    archivo.usuario_id = usuario.id
    db.session.commit()
    flash("Archivo movido correctamente.", "success")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route('/mover_archivo_modal', methods=['POST'])
def mover_archivo_modal():
    archivo_nombre = request.form.get("archivo_nombre")
    carpeta_actual = request.form.get("carpeta_actual")
    nueva_carpeta = request.form.get("nueva_carpeta")

    # Busca el archivo en la BD usando dropbox_path actual
    old_dropbox_path = f"{carpeta_actual}/{archivo_nombre}".replace('//', '/')
    archivo = Archivo.query.filter_by(dropbox_path=old_dropbox_path).first()
    if not archivo:
        flash("Archivo no encontrado", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])

    # Asegura que exista la carpeta destino
    try:
        dbx.files_create_folder_v2(nueva_carpeta)
    except dropbox.exceptions.ApiError as e:
        if "conflict" not in str(e):
            raise e

    # Mueve el archivo en Dropbox
    nuevo_destino = f"{nueva_carpeta}/{archivo.nombre}"
    dbx.files_move_v2(archivo.dropbox_path, nuevo_destino, allow_shared_folder=True, autorename=True)

    # Actualiza en BD
    archivo.dropbox_path = nuevo_destino
    db.session.commit()
    flash("Archivo movido correctamente.", "success")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))


@bp.route('/renombrar_archivo', methods=['POST'])
def renombrar_archivo():
    from app.models import Archivo
    archivo_nombre_actual = request.form.get("archivo_nombre_actual")
    carpeta_actual = request.form.get("carpeta_actual")
    usuario_id = request.form.get("usuario_id")
    nuevo_nombre = request.form.get("nuevo_nombre")

    if not (archivo_nombre_actual and carpeta_actual and usuario_id and nuevo_nombre):
        flash("Faltan datos para renombrar.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    old_path = f"{carpeta_actual}/{archivo_nombre_actual}".replace('//', '/')
    new_path = f"{carpeta_actual}/{nuevo_nombre}".replace('//', '/')

    archivo = Archivo.query.filter_by(dropbox_path=old_path).first()
    if not archivo:
        flash("Archivo no encontrado en la base de datos.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
    try:
        dbx.files_move_v2(old_path, new_path, allow_shared_folder=True, autorename=True)
    except Exception as e:
        flash(f"Error renombrando en Dropbox: {e}", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    archivo.nombre = nuevo_nombre
    archivo.dropbox_path = new_path
    db.session.commit()

    flash("Archivo renombrado correctamente.", "success")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))
