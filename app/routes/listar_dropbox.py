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
    estructura = obtener_estructura_dropbox()
    return render_template("carpetas_dropbox.html", estructura=estructura)



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