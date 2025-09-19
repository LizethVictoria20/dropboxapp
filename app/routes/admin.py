from flask import Blueprint, request, jsonify, Response, current_app
from flask_login import login_required, current_user
from app.models import Archivo
from app.dropbox_utils import descargar_desde_dropbox, generar_enlace_dropbox_temporal
from app import db
from app.routes.auth import role_required
import logging

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def preview_file_logic(file_id):
    try:
        # Buscar el archivo en la base de datos
        archivo = Archivo.query.get(file_id)
        if not archivo:
            return jsonify({"error": "Archivo no encontrado"}), 404
        
        # Verificar permisos del usuario
        if not current_user.puede_administrar() and archivo.usuario_id != current_user.id:
            return jsonify({"error": "No tienes permisos para ver este archivo"}), 403
        
        # Si el archivo tiene ruta de Dropbox, descargarlo
        if archivo.dropbox_path:
            try:
                contenido = descargar_desde_dropbox(archivo.dropbox_path)
            except Exception as e:
                logger.error(f"Error descargando archivo {archivo.dropbox_path}: {e}")
                return jsonify({"error": f"No se pudo descargar el archivo: {str(e)}"}), 500
        else:
            return jsonify({"error": "Archivo no disponible en Dropbox"}), 404
        
        # Determinar el tipo MIME basado en la extensión
        extension = archivo.nombre.split('.')[-1].lower() if '.' in archivo.nombre else ''
        
        if extension == "pdf":
            # Para PDF, devolver el contenido directamente
            return Response(contenido, mimetype="application/pdf")
        elif extension in ["jpg", "jpeg", "png", "gif"]:
            # Para imágenes, devolver el contenido directamente
            mimetype = f"image/{extension}" if extension != "jpg" else "image/jpeg"
            return Response(contenido, mimetype=mimetype)
        elif extension in ["doc", "docx"]:
            # Para documentos Word, intentar generar enlace temporal
            try:
                link_temporal = generar_enlace_dropbox_temporal(archivo.dropbox_path)
                iframe_html = f"""
                <!DOCTYPE html>
                <html>
                <head><meta charset="utf-8" /></head>
                <body style="margin:0; padding:0;">
                <iframe
                    src="https://docs.google.com/gview?embedded=true&url={link_temporal}"
                    style="width:100%; height:100vh;"
                    frameborder="0">
                </iframe>
                </body>
                </html>
                """
                return Response(iframe_html, mimetype="text/html")
            except Exception as link_error:
                logger.warning(f"No se pudo generar enlace temporal para {archivo.dropbox_path}: {link_error}")
                # Fallback: mostrar mensaje informativo
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head><meta charset="utf-8" /></head>
                <body style="margin:0; padding:0; display:flex; justify-content:center; align-items:center; background:#f5f5f5; font-family: Arial, sans-serif;">
                <div style="text-align: center; padding: 20px;">
                    <h2 style="color: #333; margin-bottom: 10px;">Documento Word</h2>
                    <p style="color: #666; margin-bottom: 20px;">El archivo {archivo.nombre} se ha descargado correctamente.</p>
                    <p style="color: #999; font-size: 14px;">Para visualizar documentos Word, se requiere el permiso 'sharing.write' en la aplicación de Dropbox.</p>
                </div>
                </body>
                </html>
                """
                return Response(html_content, mimetype="text/html")
        else:
            return jsonify({"error": f"No preview available for .{extension} files"}), 415
            
    except Exception as e:
        logger.error(f"Error en preview_file_logic para file_id {file_id}: {e}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route("/preview_file/<int:file_id>")
@login_required
def admin_preview_file(file_id):
    """
    Endpoint para previsualizar archivos locales (desde la base de datos)
    """
    return preview_file_logic(file_id)

@admin_bp.route("/preview_file", methods=["POST"])
@login_required
def admin_preview_file_dropbox():
    """
    Endpoint para previsualizar archivos directamente desde Dropbox
    """
    try:
        data = request.get_json()
        path = data.get("path")
        extension = data.get("extension", "").lower()

        if not path:
            return jsonify({"error": "Missing file path"}), 400

        # Verificar permisos del usuario
        if not current_user.puede_administrar():
            # Para usuarios no admin, verificar que el archivo pertenece a su estructura
            # Esta verificación puede ser más compleja dependiendo de tu lógica de permisos
            pass

        # Descargar contenido para visualización
        try:
            contenido = descargar_desde_dropbox(path)
        except Exception as e:
            logger.error(f"Error descargando archivo {path}: {e}")
            return jsonify({"error": f"No se pudo descargar el archivo: {str(e)}"}), 500

        if extension == "pdf":
            # Para PDF, devolver el contenido directamente
            return Response(contenido, mimetype="application/pdf")
        elif extension in ["jpg", "jpeg", "png", "gif"]:
            # Para imágenes, devolver el contenido directamente
            mimetype = f"image/{extension}" if extension != "jpg" else "image/jpeg"
            return Response(contenido, mimetype=mimetype)
        elif extension in ["doc", "docx"]:
            # Para documentos Word, generar enlace temporal si es posible
            try:
                link_temporal = generar_enlace_dropbox_temporal(path)
                iframe_html = f"""
                <!DOCTYPE html>
                <html>
                <head><meta charset="utf-8" /></head>
                <body style="margin:0; padding:0;">
                <iframe
                    src="https://docs.google.com/gview?embedded=true&url={link_temporal}"
                    style="width:100%; height:100vh;"
                    frameborder="0">
                </iframe>
                </body>
                </html>
                """
                return Response(iframe_html, mimetype="text/html")
            except Exception as link_error:
                logger.warning(f"No se pudo generar enlace temporal para {path}: {link_error}")
                # Fallback: mostrar mensaje de que el archivo se descargó
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head><meta charset="utf-8" /></head>
                <body style="margin:0; padding:0; display:flex; justify-content:center; align-items:center; background:#f5f5f5; font-family: Arial, sans-serif;">
                <div style="text-align: center; padding: 20px;">
                    <h2 style="color: #333; margin-bottom: 10px;">Documento Word</h2>
                    <p style="color: #666; margin-bottom: 20px;">El archivo {path.split('/')[-1]} se ha descargado correctamente.</p>
                    <p style="color: #999; font-size: 14px;">Para visualizar documentos Word, se requiere el permiso 'sharing.write' en la aplicación de Dropbox.</p>
                </div>
                </body>
                </html>
                """
                return Response(html_content, mimetype="text/html")
        else:
            return jsonify({"error": f"No preview available for .{extension} files"}), 415
            
    except Exception as e:
        logger.error(f"Error en admin_preview_file_dropbox: {e}")
        return jsonify({"error": str(e)}), 500 
    
@admin_bp.route("/descargar_archivo", methods=["GET"])
@login_required
def descargar_archivo():
    from flask import send_file
    import io
    archivo_id = request.args.get("archivo_id")
    dropbox_path = request.args.get("path")
    nombre_archivo = request.args.get("nombre", "documento.pdf")

    try:
        if archivo_id:
            archivo = Archivo.query.get(int(archivo_id))
            if not archivo:
                return "Archivo no encontrado", 404
            if not archivo.dropbox_path:
                return "Archivo sin ruta Dropbox", 400

            contenido = descargar_desde_dropbox(archivo.dropbox_path)
            extension = archivo.nombre.split('.')[-1].lower()
            mimetype = "application/octet-stream"
            if extension in ["pdf", "jpg", "jpeg", "png"]:
                mimetype = f"image/{extension}" if extension != "jpg" else "image/jpeg"
            elif extension == "pdf":
                mimetype = "application/pdf"

            return send_file(io.BytesIO(contenido),
                            mimetype=mimetype,
                            as_attachment=True,
                            download_name=archivo.nombre)
        elif dropbox_path:
            contenido = descargar_desde_dropbox(dropbox_path)
            return send_file(io.BytesIO(contenido),
                            mimetype="application/octet-stream",
                            as_attachment=True,
                            download_name=nombre_archivo)
        else:
            return "Falta archivo_id o path", 400
    except Exception as e:
        logger.error(f"Error descargando archivo: {e}")
        return f"Error: {e}", 500


@admin_bp.route('/fix/archivos/estado-en-revision', methods=['POST'])
@login_required
@role_required('admin')
def fix_archivos_estado_en_revision():
    """Establece estado='en_revision' en archivos sin estado definido (NULL o vacío).
    Solo para administradores.
    """
    try:
        updated = Archivo.query.filter((Archivo.estado.is_(None)) | (Archivo.estado == '')).update(
            {Archivo.estado: 'en_revision'}, synchronize_session=False
        )
        db.session.commit()
        return jsonify({
            'success': True,
            'updated': int(updated or 0)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
