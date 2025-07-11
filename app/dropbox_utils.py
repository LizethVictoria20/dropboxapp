import dropbox
from flask import current_app

def get_dbx():
    api_key = current_app.config["DROPBOX_API_KEY"]
    return dropbox.Dropbox(api_key)

def create_dropbox_folder(path):
    dbx = get_dbx()
    try:
        dbx.files_create_folder_v2(path)
    except dropbox.exceptions.ApiError as e:
        if "conflict" not in str(e):
            raise e

def move_dropbox_item(from_path, to_path):
    dbx = get_dbx()
    dbx.files_move_v2(from_path, to_path)

def rename_dropbox_item(from_path, new_name):
    to_path = '/'.join(from_path.split('/')[:-1] + [new_name])
    move_dropbox_item(from_path, to_path)
