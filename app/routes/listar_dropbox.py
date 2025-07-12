from flask import Blueprint, render_template, current_app
import dropbox

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
