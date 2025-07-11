from flask import Blueprint, render_template, current_app
import dropbox

bp = Blueprint("listar_dropbox", __name__)

def obtener_carpetas_dropbox(path="", dbx=None):
    if dbx is None:
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
    folders = []
    res = dbx.files_list_folder(path, recursive=True)
    for entry in res.entries:
        if isinstance(entry, dropbox.files.FolderMetadata):
            folders.append(entry.path_display)
    return sorted(folders)

@bp.route("/carpetas_dropbox")
def carpetas_dropbox():
    carpetas = obtener_carpetas_dropbox()
    return render_template("carpetas_dropbox.html", carpetas=carpetas)
