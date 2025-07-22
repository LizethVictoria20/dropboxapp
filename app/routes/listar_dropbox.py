from flask import Blueprint, json, jsonify, render_template, current_app, request, redirect, url_for, flash
import json
from flask_login import current_user, login_required
from app.categorias import CATEGORIAS
import dropbox
from app.models import Archivo, Beneficiario, Folder, User
from app import db
import unicodedata

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
        api_key = current_app.config.get("DROPBOX_API_KEY")
        if not api_key:
            print("Warning: DROPBOX_API_KEY no configurado, retornando estructura vacía")
            return {"_subcarpetas": {}, "_archivos": []}
        dbx = dropbox.Dropbox(api_key)
    
    try:
        # Obtener contenido del directorio actual (no recursivo)
        res = dbx.files_list_folder(path, recursive=False)
        print(f"Encontrados {len(res.entries)} elementos en '{path}'")
    except dropbox.exceptions.ApiError as e:
        print(f"Error accediendo a Dropbox path '{path}': {e}")
        # Retornar estructura vacía si el path no existe
        return {"_subcarpetas": {}, "_archivos": []}
    
    estructura = {"_subcarpetas": {}, "_archivos": []}

    for entry in res.entries:
        if isinstance(entry, dropbox.files.FolderMetadata):
            # Es una carpeta - explorar recursivamente
            print(f"  Carpeta encontrada: {entry.name}")
            sub_path = f"{path}/{entry.name}" if path else f"/{entry.name}"
            sub_estructura = obtener_estructura_dropbox(path=sub_path, dbx=dbx)
            estructura["_subcarpetas"][entry.name] = sub_estructura
        elif isinstance(entry, dropbox.files.FileMetadata):
            # Es un archivo
            estructura["_archivos"].append(entry.name)

    return estructura

def obtener_estructura_dropbox_optimizada(path="", dbx=None, max_depth=3, current_depth=0):
    """
    Versión optimizada que obtiene la estructura de forma recursiva pero con límite de profundidad
    para evitar problemas de rendimiento con estructuras muy profundas
    """
    print(f"=== obtener_estructura_dropbox_optimizada ===")
    print(f"Path: '{path}', current_depth: {current_depth}, max_depth: {max_depth}")
    
    if dbx is None:
        api_key = current_app.config.get("DROPBOX_API_KEY")
        if not api_key:
            print("Warning: DROPBOX_API_KEY no configurado, retornando estructura vacía")
            return {"_subcarpetas": {}, "_archivos": []}
        dbx = dropbox.Dropbox(api_key)
    
    # Limitar la profundidad para evitar recursión infinita
    if current_depth >= max_depth:
        print(f"Alcanzada profundidad máxima ({max_depth}) para path: '{path}'")
        return {"_subcarpetas": {}, "_archivos": []}
    
    try:
        print(f"Llamando a Dropbox API para path: '{path}'")
        # Si el path está vacío, usar la raíz de Dropbox
        if not path or path == "":
            path = ""
            print("Path vacío, usando raíz de Dropbox")
        
        res = dbx.files_list_folder(path, recursive=False)
        print(f"Encontrados {len(res.entries)} elementos en '{path}'")
        print(f"Entries: {[entry.name for entry in res.entries]}")
        
        # Debug adicional para ver qué tipo de entradas son
        for i, entry in enumerate(res.entries):
            print(f"  Entry {i}: {entry.name} - Tipo: {type(entry).__name__}")
            if isinstance(entry, dropbox.files.FolderMetadata):
                print(f"    Es carpeta: {entry.name}")
            elif isinstance(entry, dropbox.files.FileMetadata):
                print(f"    Es archivo: {entry.name}")
    except dropbox.exceptions.ApiError as e:
        print(f"Error accediendo a Dropbox path '{path}': {e}")
        # Re-lanzar el error para que sea manejado por el llamador
        raise e
    except Exception as e:
        print(f"Error inesperado accediendo a Dropbox path '{path}': {e}")
        raise e
    
    estructura = {"_subcarpetas": {}, "_archivos": []}

    for entry in res.entries:
        if isinstance(entry, dropbox.files.FolderMetadata):
            # Es una carpeta - explorar recursivamente
            print(f"  Carpeta encontrada: {entry.name}")
            sub_path = f"{path}/{entry.name}" if path else f"/{entry.name}"
            try:
                sub_estructura = obtener_estructura_dropbox_optimizada(
                    path=sub_path, 
                    dbx=dbx, 
                    max_depth=max_depth, 
                    current_depth=current_depth + 1
                )
                estructura["_subcarpetas"][entry.name] = sub_estructura
            except Exception as e:
                print(f"Error explorando subcarpeta '{sub_path}': {e}")
                # Continuar con otras carpetas aunque una falle
                estructura["_subcarpetas"][entry.name] = {"_subcarpetas": {}, "_archivos": []}
        elif isinstance(entry, dropbox.files.FileMetadata):
            # Es un archivo
            print(f"  Archivo encontrado: {entry.name}")
            estructura["_archivos"].append(entry.name)

    print(f"Estructura final para '{path}': {len(estructura['_subcarpetas'])} carpetas, {len(estructura['_archivos'])} archivos")
    print(f"Estructura completa: {estructura}")
    return estructura

def filtra_arbol_por_rutas(estructura, rutas_visibles, prefix, usuario_email):
    """
    Recorta el árbol (estructura) dejando solo las subcarpetas cuya ruta esté en rutas_visibles.
    - estructura: dict con formato {'_archivos': [...], '_subcarpetas': { ... }}
    - rutas_visibles: set con paths permitidos
    - prefix: path base actual (ej: /user@email.com)
    - usuario_email: email para manejo especial de raíz
    """
    if not estructura:
        return estructura
    nueva_estructura = {"_archivos": [], "_subcarpetas": {}}
    # Archivos siempre se muestran si el padre es visible
    if prefix in rutas_visibles:
        nueva_estructura["_archivos"] = estructura.get("_archivos", [])
    else:
        nueva_estructura["_archivos"] = []

    for subcarpeta, contenido in estructura.get("_subcarpetas", {}).items():
        # Si estamos en el path raíz del usuario y el subnivel es el email, unwrap (evita doble email)
        if prefix.rstrip("/") == f"/{usuario_email}" and subcarpeta == usuario_email:
            # Desempaqueta ese nivel y sigue con los hijos directos
            for sub_subcarpeta, sub_contenido in contenido.get("_subcarpetas", {}).items():
                ruta_actual = prefix.rstrip("/") + "/" + sub_subcarpeta
                if ruta_actual in rutas_visibles:
                    nueva_estructura["_subcarpetas"][sub_subcarpeta] = filtra_arbol_por_rutas(
                        sub_contenido, rutas_visibles, ruta_actual, usuario_email
                    )
            continue

        ruta_actual = prefix.rstrip("/") + "/" + subcarpeta
        if ruta_actual in rutas_visibles:
            nueva_estructura["_subcarpetas"][subcarpeta] = filtra_arbol_por_rutas(
                contenido, rutas_visibles, ruta_actual, usuario_email
            )
    return nueva_estructura


@bp.route("/carpetas_dropbox")
@login_required
def carpetas_dropbox():
    try:
        estructuras_usuarios = {}
        
        # Verificar configuración de Dropbox
        api_key = current_app.config.get("DROPBOX_API_KEY")
        if not api_key:
            flash("Error: Configuración de Dropbox no disponible.", "error")
            return render_template("carpetas_dropbox.html", 
                                 estructuras_usuarios={},
                                 usuarios={},
                                 usuario_actual=current_user,
                                 estructuras_usuarios_json="{}",
                                 usuarios_emails_json="{}",
                                 folders_por_ruta={})
        
        dbx = dropbox.Dropbox(api_key)

        # Determina qué usuarios cargar
        if current_user.rol == "admin" or current_user.rol == "superadmin":
            usuarios = User.query.all()
            # Admin ve todas las carpetas
            folders = Folder.query.all()
        elif current_user.rol == "lector":
            # Lector puede ver todas las carpetas de todos los usuarios
            usuarios = User.query.all()
            folders = Folder.query.all()
        elif current_user.rol == "cliente":
            # Cliente ve solo sus propias carpetas (no beneficiarios en la vista principal)
            usuarios = [current_user]
            
            # Obtener carpetas del cliente y sus beneficiarios (para permisos)
            beneficiarios = Beneficiario.query.filter_by(titular_id=current_user.id).all()
            user_ids = [current_user.id] + [b.id for b in beneficiarios]
            folders = Folder.query.filter(Folder.user_id.in_(user_ids)).all()
        else:
            # Otros roles
            usuarios = [current_user]
            folders = Folder.query.filter_by(user_id=current_user.id, es_publica=True).all()

        usuarios_dict = {u.id: u for u in usuarios}
        folders_por_ruta = {f.dropbox_path: f for f in folders}

        for user in usuarios:
            # Crear carpeta raíz si no existe
            if not user.dropbox_folder_path:
                if hasattr(user, 'email'):  # Es un User
                    user.dropbox_folder_path = f"/{user.email}"
                else:  # Es un Beneficiario
                    user.dropbox_folder_path = f"/{user.titular.email}/{user.nombre}"
                
                try:
                    dbx.files_create_folder_v2(user.dropbox_folder_path)
                except dropbox.exceptions.ApiError as e:
                    if "conflict" not in str(e):
                        raise e
                db.session.commit()

            path = user.dropbox_folder_path
            try:
                # Usar la función optimizada con recursión limitada para mejor rendimiento
                estructura = obtener_estructura_dropbox_optimizada(path=path, max_depth=5)
            except Exception as e:
                user_identifier = user.email if hasattr(user, 'email') else user.nombre
                print(f"Error obteniendo estructura para usuario {user_identifier}: {e}")
                estructura = {"_subcarpetas": {}, "_archivos": []}
            
            # Filtrar la estructura según los permisos del usuario
            if current_user.rol == "cliente":
                # Para clientes, mostrar todo (ya están filtrados por usuario)
                # No necesitamos filtrar más porque solo cargamos sus carpetas
                pass
            elif current_user.rol == "lector":
                # Para lectores, mostrar todas las carpetas sin filtrar
                pass
            elif current_user.rol != "admin" and current_user.rol != "superadmin":
                # Para otros roles, solo mostrar carpetas públicas
                rutas_visibles = set(folders_por_ruta.keys())
                user_identifier = user.email if hasattr(user, 'email') else user.nombre
                estructura = filtra_arbol_por_rutas(estructura, rutas_visibles, path, user_identifier)
            
            estructuras_usuarios[user.id] = estructura

        # Crear un diccionario con los emails de los usuarios
        usuarios_emails = {}
        for user in usuarios:
            if hasattr(user, 'email'):
                usuarios_emails[user.id] = user.email
            else:
                # Para beneficiarios, usar el email del titular
                usuarios_emails[user.id] = user.titular.email if hasattr(user, 'titular') else str(user.id)
        
        return render_template(
            "carpetas_dropbox.html",
            estructuras_usuarios=estructuras_usuarios,
            usuarios=usuarios_dict,
            usuario_actual=current_user,
            estructuras_usuarios_json=json.dumps(estructuras_usuarios),
            usuarios_emails_json=json.dumps(usuarios_emails),
            folders_por_ruta=folders_por_ruta,
        )
        
    except Exception as e:
        print(f"Error general en carpetas_dropbox: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error al cargar carpetas: {str(e)}", "error")
        return render_template("carpetas_dropbox.html", 
                             estructuras_usuarios={},
                             usuarios={},
                             usuario_actual=current_user,
                             estructuras_usuarios_json="{}",
                             usuarios_emails_json="{}",
                             folders_por_ruta={})

@bp.route("/api/carpeta_info/<path:ruta>")
@login_required
def obtener_info_carpeta(ruta):
    """Endpoint para obtener información de una carpeta específica"""
    from app.models import Folder
    
    # Buscar la carpeta en la base de datos
    carpeta = Folder.query.filter_by(dropbox_path=f"/{ruta}").first()
    
    if carpeta:
        return jsonify({
            'existe': True,
            'es_publica': carpeta.es_publica,
            'nombre': carpeta.name,
            'usuario_id': carpeta.user_id
        })
    else:
        return jsonify({
            'existe': False,
            'es_publica': True,  # Por defecto pública si no existe en BD
            'nombre': ruta.split('/')[-1] if '/' in ruta else ruta,
            'usuario_id': None
        })

@bp.route("/api/carpeta_contenido/<path:ruta>")
@login_required
def obtener_contenido_carpeta(ruta):
    """Endpoint para obtener el contenido de una carpeta específica"""
    print(f"API: Obteniendo contenido de carpeta: {ruta}")
    try:
        # Verificar permisos
        if current_user.rol == "cliente":
            # Cliente solo puede ver sus propias carpetas y las de sus beneficiarios
            user_ids = [current_user.id]
            beneficiarios = Beneficiario.query.filter_by(titular_id=current_user.id).all()
            user_ids.extend([b.id for b in beneficiarios])
            
            # Verificar que la carpeta pertenece al cliente o sus beneficiarios
            carpeta = Folder.query.filter_by(dropbox_path=f"/{ruta}").first()
            if carpeta and carpeta.user_id not in user_ids:
                print(f"API: Permiso denegado para carpeta {ruta}")
                return jsonify({"success": False, "error": "No tienes permisos para acceder a esta carpeta"}), 403
        elif current_user.rol == "lector":
            # Lector puede ver todas las carpetas
            pass
        elif current_user.rol == "admin" or current_user.rol == "superadmin":
            # Admin puede ver todas las carpetas
            pass
        
        # Obtener estructura de la carpeta
        print(f"API: Creando cliente Dropbox para ruta: {ruta}")
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        print(f"API: Llamando a obtener_estructura_dropbox_optimizada con path: /{ruta}")
        
        try:
            estructura = obtener_estructura_dropbox_optimizada(path=f"/{ruta}", dbx=dbx, max_depth=3)
        except dropbox.exceptions.ApiError as e:
            print(f"API: Error de Dropbox API para ruta {ruta}: {e}")
            if "not_found" in str(e):
                return jsonify({"success": False, "error": "Carpeta no encontrada en Dropbox"}), 404
            elif "insufficient_scope" in str(e):
                return jsonify({"success": False, "error": "Permisos insuficientes para acceder a esta carpeta"}), 403
            else:
                return jsonify({"success": False, "error": f"Error de Dropbox: {str(e)}"}), 500
        except Exception as e:
            print(f"API: Error inesperado obteniendo estructura para {ruta}: {e}")
            return jsonify({"success": False, "error": f"Error interno: {str(e)}"}), 500
        
        # Determinar el usuario_id basado en la ruta
        usuario_id = None
        if current_user.rol == "cliente":
            # Para clientes, el usuario_id será el del cliente actual
            usuario_id = current_user.id
        
        print(f"API: Retornando estructura para {ruta}: {len(estructura.get('_subcarpetas', {}))} carpetas, {len(estructura.get('_archivos', []))} archivos")
        return jsonify({
            "success": True,
            "estructura": estructura,
            "usuario_id": usuario_id
        })
        
    except Exception as e:
        print(f"Error general obteniendo contenido de carpeta {ruta}: {e}")
        return jsonify({"success": False, "error": f"Error de conexión: {str(e)}"}), 500


@bp.route("/crear_carpeta", methods=["POST"])
def crear_carpeta():
    # Verificar permisos del lector
    if current_user.rol == 'lector' and not current_user.puede_modificar_archivos():
        flash("No tienes permisos para crear carpetas.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    nombre = request.form.get("nombre")
    padre = request.form.get("padre", "")
    es_publica = request.form.get("es_publica", "true").lower() == "true"  # Por defecto pública
    
    if not nombre:
        flash("El nombre de la carpeta es obligatorio.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    # Construir la ruta en Dropbox
    ruta = padre.rstrip("/") + "/" + nombre if padre else "/" + nombre
    
    try:
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        dbx.files_create_folder_v2(ruta)
        
        # Guardar carpeta en la base de datos
        nueva_carpeta = Folder(
            name=nombre,
            user_id=current_user.id,
            dropbox_path=ruta,
            es_publica=es_publica
        )
        db.session.add(nueva_carpeta)
        db.session.commit()
        
        # Registrar actividad
        current_user.registrar_actividad('folder_created', f'Carpeta "{nombre}" creada en {ruta}')
        
        tipo_carpeta = "pública" if es_publica else "privada"
        flash(f"Carpeta '{ruta}' creada correctamente como {tipo_carpeta}.", "success")
    except dropbox.exceptions.ApiError as e:
        flash(f"Error creando carpeta: {e}", "error")
    except Exception as e:
        flash(f"Error guardando carpeta en base de datos: {e}", "error")
        
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

def normaliza(nombre):
    nfkd = unicodedata.normalize('NFKD', nombre or '')
    solo_ascii = u"".join([c for c in nfkd if not unicodedata.combining(c)])
    return solo_ascii.upper().strip().replace(" ", "_")

@bp.route("/subir_archivo", methods=["GET", "POST"])
def subir_archivo():
    from app.models import User, Beneficiario, Archivo, Folder
    import json

    if request.method == "GET":
        print("GET: Mostrando formulario de subida")
        
        # Filtrar usuarios según el rol del usuario actual
        if current_user.rol == "cliente":
            # Cliente solo ve sus propias carpetas
            titulares = [current_user]  # Solo el usuario actual
            beneficiarios = Beneficiario.query.filter_by(titular_id=current_user.id).all()
        elif current_user.rol in ["admin", "superadmin"]:
            # Admin ve todos los usuarios titulares (no beneficiarios)
            titulares = User.query.filter_by(es_beneficiario=False).all()
            beneficiarios = Beneficiario.query.all()
        else:
            # Otros roles (lector, etc.) - ajustar según necesidades
            titulares = User.query.filter_by(es_beneficiario=False).all()
            beneficiarios = Beneficiario.query.all()
        
        print("Usuarios en DB:", [u.email for u in titulares])
        print("Beneficiarios en DB:", [b.email for b in beneficiarios])
        return render_template(
            "subir_archivo.html",
            categorias=CATEGORIAS.keys(),
            categorias_json=json.dumps(CATEGORIAS),
            titulares=titulares,
            beneficiarios=beneficiarios
        )

    print("POST: Procesando subida de archivo")
    
    # Obtener datos del formulario
    usuario_id = request.form.get("usuario_id")
    categoria = request.form.get("categoria")
    subcategoria = request.form.get("subcategoria")
    archivo = request.files.get("archivo")
    
    print("usuario_id recibido:", usuario_id)
    print("Categoría recibida:", categoria)
    print("Subcategoría recibida:", subcategoria)
    print("Archivo recibido:", archivo.filename if archivo else None)

    # Validar campos obligatorios
    if not (usuario_id and categoria and subcategoria and archivo):
        print("ERROR: Faltan campos obligatorios")
        flash("Completa todos los campos obligatorios", "error")
        return redirect(url_for("listar_dropbox.subir_archivo"))

    # Validar y obtener usuario/beneficiario
    usuario = None
    try:
        print(f"DEBUG: Procesando usuario_id: '{usuario_id}' (tipo: {type(usuario_id)})")
        print(f"DEBUG: usuario_id.startswith('user-'): {usuario_id.startswith('user-')}")
        print(f"DEBUG: usuario_id.startswith('beneficiario-'): {usuario_id.startswith('beneficiario-')}")
        
        if usuario_id.startswith("user-"):
            real_id = int(usuario_id[5:])
            usuario = User.query.get(real_id)
            print(f"Es titular (User), id extraído: {real_id}, usuario encontrado: {usuario is not None}")
        elif usuario_id.startswith("beneficiario-"):
            real_id = int(usuario_id[13:])
            usuario = Beneficiario.query.get(real_id)
            print(f"Es beneficiario, id extraído: {real_id}, beneficiario encontrado: {usuario is not None}")
        else:
            print(f"usuario_id inválido: '{usuario_id}' (no tiene prefijo válido)")
            flash("Formato de usuario inválido. Debe seleccionar un usuario del formulario.", "error")
            return redirect(url_for("listar_dropbox.subir_archivo"))
    except (ValueError, IndexError) as e:
        print(f"Error al procesar usuario_id: {e}")
        flash("Error al procesar el usuario seleccionado", "error")
        return redirect(url_for("listar_dropbox.subir_archivo"))

    if not usuario:
        print("ERROR: Usuario no encontrado o inválido")
        flash("Usuario no encontrado en la base de datos", "error")
        return redirect(url_for("listar_dropbox.subir_archivo"))

    # Validación de seguridad: cliente solo puede subir a sus propias carpetas
    if current_user.rol == "cliente":
        if usuario_id.startswith("user-"):
            # Si es un titular, debe ser el usuario actual
            if int(usuario_id[5:]) != current_user.id:
                flash("No tienes permisos para subir archivos a esta carpeta.", "error")
                return redirect(url_for("listar_dropbox.subir_archivo"))
        elif usuario_id.startswith("beneficiario-"):
            # Si es un beneficiario, debe pertenecer al usuario actual
            beneficiario_id = int(usuario_id[13:])
            beneficiario = Beneficiario.query.get(beneficiario_id)
            if not beneficiario or beneficiario.titular_id != current_user.id:
                flash("No tienes permisos para subir archivos a esta carpeta.", "error")
                return redirect(url_for("listar_dropbox.subir_archivo"))

    # Leer el archivo una sola vez
    archivo_content = archivo.read()
    archivo.seek(0)  # Resetear el puntero del archivo para futuras lecturas

    try:
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        
        # Carpeta raíz de usuario/beneficiario
        if hasattr(usuario, "dropbox_folder_path") and usuario.dropbox_folder_path:
            carpeta_usuario = usuario.dropbox_folder_path
            print("Carpeta raíz ya existe:", carpeta_usuario)
        else:
            carpeta_usuario = f"/{usuario.email}"
            print("Creando carpeta raíz para usuario:", carpeta_usuario)
            try:
                dbx.files_create_folder_v2(carpeta_usuario)
                print("Carpeta raíz creada en Dropbox")
            except dropbox.exceptions.ApiError as e:
                if "conflict" not in str(e):
                    print("ERROR al crear carpeta raíz en Dropbox:", e)
                    raise e
                print("La carpeta raíz ya existía en Dropbox")
            
            # Guardar ruta en la base de datos
            if hasattr(usuario, "dropbox_folder_path"):
                usuario.dropbox_folder_path = carpeta_usuario
                db.session.commit()
                print("Ruta raíz guardada en DB:", carpeta_usuario)

        # Crear categoría y subcategoría
        ruta_categoria = f"{carpeta_usuario}/{categoria}"
        try:
            dbx.files_create_folder_v2(ruta_categoria)
            print("Carpeta categoría creada:", ruta_categoria)
            
            # Guardar carpeta categoría en la base de datos
            carpeta_cat = Folder(
                name=categoria,
                user_id=getattr(usuario, "id", None),
                dropbox_path=ruta_categoria,
                es_publica=True
            )
            db.session.add(carpeta_cat)
            
        except dropbox.exceptions.ApiError as e:
            if "conflict" not in str(e):
                print("ERROR al crear carpeta categoría:", e)
                raise e
            print("La carpeta categoría ya existía:", ruta_categoria)
            
        ruta_subcat = f"{ruta_categoria}/{subcategoria}"
        try:
            dbx.files_create_folder_v2(ruta_subcat)
            print("Carpeta subcategoría creada:", ruta_subcat)
            
            # Guardar carpeta subcategoría en la base de datos
            carpeta_subcat = Folder(
                name=subcategoria,
                user_id=getattr(usuario, "id", None),
                dropbox_path=ruta_subcat,
                es_publica=True
            )
            db.session.add(carpeta_subcat)
            
        except dropbox.exceptions.ApiError as e:
            if "conflict" not in str(e):
                print("ERROR al crear carpeta subcategoría:", e)
                raise e
            print("La carpeta subcategoría ya existía:", ruta_subcat)

        # Generar nombre final del archivo
        nombre_evidencia = categoria.upper().replace(" ", "_")
        nombre_original = archivo.filename
        ext = ""
        if "." in nombre_original:
            ext = "." + nombre_original.rsplit(".", 1)[1].lower()

        # Determinar tipo de usuario y generar nombre
        if isinstance(usuario, User) and not getattr(usuario, "es_beneficiario", False):
            # TITULAR
            nombre_titular = normaliza(usuario.nombre or usuario.email.split('@')[0])
            nombre_final = f"{nombre_evidencia}_TITULAR_{nombre_titular}{ext}"
        elif isinstance(usuario, Beneficiario):
            # BENEFICIARIO
            nombre_ben = normaliza(usuario.nombre)
            if hasattr(usuario, "titular") and usuario.titular:
                nombre_titular = normaliza(usuario.titular.nombre)
            else:
                nombre_titular = "SIN_TITULAR"
            nombre_final = f"{nombre_evidencia}_BENEFICIARIO_{nombre_ben}_TITULAR_{nombre_titular}{ext}"
        else:
            # Usuario genérico
            nombre_final = f"{nombre_evidencia}_SINROL_{normaliza(usuario.nombre or usuario.email.split('@')[0])}{ext}"

        print("DEBUG | Nombre final para guardar/subir:", nombre_final)

        # Subir archivo con nombre final
        dropbox_dest = f"{ruta_subcat}/{nombre_final}"
        dbx.files_upload(archivo_content, dropbox_dest, mode=dropbox.files.WriteMode("overwrite"))
        print("Archivo subido exitosamente a Dropbox:", dropbox_dest)

        # Guardar en la base de datos
        nuevo_archivo = Archivo(
            nombre=archivo.filename,
            categoria=categoria,
            subcategoria=subcategoria,
            dropbox_path=dropbox_dest,
            usuario_id=getattr(usuario, "id", None)
        )
        db.session.add(nuevo_archivo)
        db.session.commit()
        print("Archivo registrado en la base de datos con ID:", nuevo_archivo.id)

        # Registrar actividad
        current_user.registrar_actividad('file_uploaded', f'Archivo "{archivo.filename}" subido a {categoria}/{subcategoria}')

        # Redirección correcta según si es AJAX o no
        redirect_url = url_for("listar_dropbox.carpetas_dropbox")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": True, "redirectUrl": redirect_url})
        else:
            flash("Archivo subido y registrado exitosamente.", "success")
            return redirect(redirect_url)


    except Exception as e:
        db.session.rollback()
        print(f"ERROR general en subida de archivo: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "error": str(e)}), 500
        else:
            flash(f"Error al subir archivo: {str(e)}", "error")
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
    
    # Registrar actividad
    current_user.registrar_actividad('file_moved', f'Archivo "{archivo_nombre}" movido a {categoria}/{subcategoria}')
    
    flash("Archivo movido correctamente.", "success")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route('/mover_archivo_modal', methods=['POST'])
@login_required
def mover_archivo_modal():
    """Mueve un archivo de una carpeta a otra usando Dropbox API"""
    
    # Verificar permisos del lector
    if current_user.rol == 'lector' and not current_user.puede_mover_archivos():
        flash("No tienes permisos para mover archivos.", "error")
        redirect_url = request.form.get("redirect_url", "")
        if redirect_url and "/usuario/" in redirect_url:
            return redirect(redirect_url)
        else:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    try:
        archivo_nombre = request.form.get("archivo_nombre")
        carpeta_actual = request.form.get("carpeta_actual")
        nueva_carpeta = request.form.get("nueva_carpeta")
        
        print(f"DEBUG | Movimiento solicitado:")
        print(f"  Archivo: {archivo_nombre}")
        print(f"  Carpeta actual: {carpeta_actual}")
        print(f"  Nueva carpeta: {nueva_carpeta}")
        print(f"  Tipo nueva_carpeta: {type(nueva_carpeta)}")
        print(f"  Longitud nueva_carpeta: {len(nueva_carpeta) if nueva_carpeta else 'None'}")
        
        # Obtener la URL de redirección
        redirect_url = request.form.get("redirect_url", "")
        
        if not all([archivo_nombre, carpeta_actual, nueva_carpeta]):
            flash("Faltan datos requeridos para mover el archivo", "error")
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
        # Limpiar y normalizar la ruta de la nueva carpeta
        nueva_carpeta = nueva_carpeta.strip()
        if not nueva_carpeta.startswith('/'):
            nueva_carpeta = '/' + nueva_carpeta
        
        print(f"DEBUG | Nueva carpeta normalizada: '{nueva_carpeta}'")
        
        # Buscar archivo en Dropbox directamente (fuente de verdad)
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        
        # Debug: Listar carpetas disponibles para verificar
        try:
            print(f"DEBUG | Listando carpetas disponibles en Dropbox...")
            root_folders = dbx.files_list_folder("", recursive=False)
            available_folders = []
            for entry in root_folders.entries:
                if isinstance(entry, dropbox.files.FolderMetadata):
                    available_folders.append(entry.path_display)
            print(f"DEBUG | Carpetas disponibles en raíz: {available_folders}")
        except Exception as e:
            print(f"DEBUG | Error listando carpetas: {e}")
        
        # Buscar el archivo en Dropbox
        try:
            search_result = dbx.files_search_v2(query=archivo_nombre)
            archivo_encontrado = None
            
            print(f"DEBUG | Buscando archivo '{archivo_nombre}' en Dropbox...")
            print(f"DEBUG | Coincidencias encontradas: {len(search_result.matches)}")
            
            for match in search_result.matches:
                # Obtener el path correcto del metadata
                if hasattr(match.metadata, 'path_display'):
                    path = match.metadata.path_display
                elif hasattr(match.metadata, 'path_lower'):
                    path = match.metadata.path_lower
                else:
                    path = str(match.metadata)
                
                print(f"DEBUG | Revisando: {path}")
                # Verificar si está en la carpeta actual
                if carpeta_actual and carpeta_actual in path:
                    archivo_encontrado = match.metadata
                    print(f"DEBUG | Archivo encontrado en carpeta actual: {path}")
                    break
            
            if not archivo_encontrado:
                # Si no se encuentra en la carpeta específica, usar la primera coincidencia
                if search_result.matches:
                    archivo_encontrado = search_result.matches[0].metadata
                    if hasattr(archivo_encontrado, 'path_display'):
                        path = archivo_encontrado.path_display
                    elif hasattr(archivo_encontrado, 'path_lower'):
                        path = archivo_encontrado.path_lower
                    else:
                        path = str(archivo_encontrado)
                    print(f"DEBUG | Usando primera coincidencia: {path}")
            
            if not archivo_encontrado:
                flash(f"Archivo '{archivo_nombre}' no encontrado en Dropbox", "error")
                if redirect_url and "/usuario/" in redirect_url:
                    return redirect(redirect_url)
                else:
                    return redirect(url_for("listar_dropbox.carpetas_dropbox"))
            
            # Debug: Mostrar información del archivo encontrado
            print(f"DEBUG | Archivo encontrado:")
            print(f"  Tipo: {type(archivo_encontrado)}")
            print(f"  Atributos disponibles: {[attr for attr in dir(archivo_encontrado) if not attr.startswith('_')]}")
            if hasattr(archivo_encontrado, 'metadata'):
                print(f"  Metadata tipo: {type(archivo_encontrado.metadata)}")
                print(f"  Metadata atributos: {[attr for attr in dir(archivo_encontrado.metadata) if not attr.startswith('_')]}")
                if hasattr(archivo_encontrado.metadata, 'path_display'):
                    print(f"  Metadata path_display: {archivo_encontrado.metadata.path_display}")
                if hasattr(archivo_encontrado.metadata, 'path_lower'):
                    print(f"  Metadata path_lower: {archivo_encontrado.metadata.path_lower}")
            else:
                print(f"  No tiene atributo 'metadata'")
                if hasattr(archivo_encontrado, 'path_display'):
                    print(f"  path_display directo: {archivo_encontrado.path_display}")
                if hasattr(archivo_encontrado, 'path_lower'):
                    print(f"  path_lower directo: {archivo_encontrado.path_lower}")
            
            # Verificar que la carpeta destino existe
            print(f"DEBUG | Verificando existencia de carpeta destino: '{nueva_carpeta}'")
            try:
                metadata_destino = dbx.files_get_metadata(nueva_carpeta)
                if not isinstance(metadata_destino, dropbox.files.FolderMetadata):
                    flash(f"El destino '{nueva_carpeta}' no es una carpeta válida", "error")
                    return redirect(url_for("listar_dropbox.carpetas_dropbox"))
                
                # Obtener el path correcto del metadata
                if hasattr(metadata_destino, 'path_display'):
                    destino_path = metadata_destino.path_display
                elif hasattr(metadata_destino, 'path_lower'):
                    destino_path = metadata_destino.path_lower
                else:
                    destino_path = str(metadata_destino)
                
                print(f"DEBUG | Carpeta destino verificada: {destino_path}")
            except Exception as e:
                # Manejar cualquier error al verificar la carpeta destino
                print(f"ERROR | Error verificando carpeta destino '{nueva_carpeta}': {e}")
                print(f"ERROR | Tipo de error: {type(e)}")
                
                # Verificar si es un error de Dropbox específico
                if hasattr(e, 'error') and hasattr(e.error, 'is_not_found') and e.error.is_not_found():
                    flash(f"La carpeta destino '{nueva_carpeta}' no existe en Dropbox", "error")
                elif "not_found" in str(e).lower():
                    flash(f"La carpeta destino '{nueva_carpeta}' no existe en Dropbox", "error")
                else:
                    flash(f"Error verificando carpeta destino '{nueva_carpeta}': {str(e)}", "error")
                
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
            
            # Obtener el path correcto del archivo encontrado
            archivo_path = None
            
            print(f"DEBUG | Intentando extraer path del archivo...")
            
            # Caso 1: El objeto es directamente un FileMetadata
            if hasattr(archivo_encontrado, 'path_display'):
                archivo_path = archivo_encontrado.path_display
                print(f"DEBUG | Path obtenido de path_display directo: {archivo_path}")
            elif hasattr(archivo_encontrado, 'path_lower'):
                archivo_path = archivo_encontrado.path_lower
                print(f"DEBUG | Path obtenido de path_lower directo: {archivo_path}")
            
            # Caso 2: El objeto tiene un atributo metadata
            if not archivo_path and hasattr(archivo_encontrado, 'metadata'):
                print(f"DEBUG | Buscando path en metadata...")
                if hasattr(archivo_encontrado.metadata, 'path_display'):
                    archivo_path = archivo_encontrado.metadata.path_display
                    print(f"DEBUG | Path obtenido de metadata.path_display: {archivo_path}")
                elif hasattr(archivo_encontrado.metadata, 'path_lower'):
                    archivo_path = archivo_encontrado.metadata.path_lower
                    print(f"DEBUG | Path obtenido de metadata.path_lower: {archivo_path}")
            
            # Caso 3: El objeto es un MetadataV2 con metadata anidado
            if not archivo_path and hasattr(archivo_encontrado, 'metadata') and hasattr(archivo_encontrado.metadata, 'metadata'):
                print(f"DEBUG | Buscando path en metadata.metadata...")
                nested_metadata = archivo_encontrado.metadata.metadata
                if hasattr(nested_metadata, 'path_display'):
                    archivo_path = nested_metadata.path_display
                    print(f"DEBUG | Path obtenido de metadata.metadata.path_display: {archivo_path}")
                elif hasattr(nested_metadata, 'path_lower'):
                    archivo_path = nested_metadata.path_lower
                    print(f"DEBUG | Path obtenido de metadata.metadata.path_lower: {archivo_path}")
            
            # Caso 4: Intentar convertir el objeto a string y extraer el path
            if not archivo_path:
                print(f"DEBUG | Intentando extraer path de la representación del objeto...")
                obj_str = str(archivo_encontrado)
                print(f"DEBUG | Representación del objeto: {obj_str}")
                
                # Buscar patrones de path en la representación
                import re
                path_patterns = [
                    r"path_display='([^']+)'",
                    r"path_lower='([^']+)'",
                    r"path_display=\"([^\"]+)\"",
                    r"path_lower=\"([^\"]+)\""
                ]
                
                for pattern in path_patterns:
                    match = re.search(pattern, obj_str)
                    if match:
                        archivo_path = match.group(1)
                        print(f"DEBUG | Path extraído con regex: {archivo_path}")
                        break
            
            # Verificar que se obtuvo un path válido
            if not archivo_path:
                print(f"ERROR | No se pudo obtener el path del archivo")
                print(f"ERROR | Objeto completo: {archivo_encontrado}")
                print(f"ERROR | Tipo de objeto: {type(archivo_encontrado)}")
                flash(f"No se pudo obtener la ruta del archivo '{archivo_nombre}'", "error")
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
            
            # Asegurar que el path sea una cadena válida
            archivo_path = str(archivo_path)
            print(f"DEBUG | Path final del archivo: '{archivo_path}'")
            
            # Construir path destino
            new_dropbox_path = f"{nueva_carpeta.rstrip('/')}/{archivo_nombre}"
            
            # Mover el archivo usando Dropbox API
            print(f"DEBUG | Moviendo archivo en Dropbox...")
            print(f"  Desde: {archivo_path}")
            print(f"  Hacia: {new_dropbox_path}")
            
            result = dbx.files_move_v2(
                from_path=archivo_path,
                to_path=new_dropbox_path,
                allow_shared_folder=True,
                autorename=True
            )
            
            # Obtener el path del resultado
            if hasattr(result.metadata, 'path_display'):
                result_path = result.metadata.path_display
            elif hasattr(result.metadata, 'path_lower'):
                result_path = result.metadata.path_lower
            else:
                result_path = str(result.metadata)
            
            print(f"DEBUG | Archivo movido exitosamente: {result_path}")
            
            # Actualizar o crear registro en la base de datos
            archivo_bd = Archivo.query.filter_by(dropbox_path=archivo_path).first()
            
            if archivo_bd:
                # Actualizar registro existente
                archivo_bd.dropbox_path = result_path
                print(f"DEBUG | Registro actualizado en BD: {archivo_bd.nombre}")
            else:
                # Crear nuevo registro
                path_parts = result_path.split('/')
                if len(path_parts) >= 4:
                    usuario_email = path_parts[1]
                    categoria = path_parts[2] if len(path_parts) > 2 else ""
                    subcategoria = path_parts[3] if len(path_parts) > 3 else ""
                    
                    usuario = User.query.filter_by(email=usuario_email).first()
                    if usuario:
                        nuevo_archivo = Archivo(
                            nombre=archivo_nombre,
                            dropbox_path=result_path,
                            categoria=categoria,
                            subcategoria=subcategoria,
                            usuario_id=usuario.id
                        )
                        db.session.add(nuevo_archivo)
                        print(f"DEBUG | Nuevo registro creado en BD: {nuevo_archivo.nombre}")
            
            db.session.commit()
            print(f"DEBUG | Base de datos actualizada")
            
            # Registrar actividad
            current_user.registrar_actividad('file_moved', f'Archivo "{archivo_nombre}" movido de {archivo_path} a {result_path}')
            
            
            # Redirigir a la URL apropiada
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
            
        except Exception as e:
            print(f"ERROR | Error de Dropbox API: {e}")
            print(f"ERROR | Tipo de error: {type(e)}")
            
            # Verificar diferentes tipos de errores
            if hasattr(e, 'error'):
                if hasattr(e.error, 'is_conflict') and e.error.is_conflict():
                    flash("Ya existe un archivo con ese nombre en la carpeta destino", "error")
                elif hasattr(e.error, 'is_insufficient_space') and e.error.is_insufficient_space():
                    flash("No hay espacio suficiente en Dropbox", "error")
                elif hasattr(e.error, 'is_not_found') and e.error.is_not_found():
                    flash("El archivo o carpeta no fue encontrado en Dropbox", "error")
                else:
                    flash(f"Error moviendo archivo en Dropbox: {e.error}", "error")
            else:
                # Manejar errores que no son ApiError
                error_msg = str(e)
                if "not_found" in error_msg.lower():
                    flash("El archivo o carpeta no fue encontrado en Dropbox", "error")
                elif "conflict" in error_msg.lower():
                    flash("Ya existe un archivo con ese nombre en la carpeta destino", "error")
                else:
                    flash(f"Error moviendo archivo: {error_msg}", "error")
            
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
    except Exception as e:
        print(f"ERROR | Error general en mover_archivo_modal: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error moviendo archivo: {e}", "error")
    
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))


@bp.route('/renombrar_archivo', methods=['POST'])
def renombrar_archivo():
    from app.models import Archivo
    
    # Verificar permisos del lector
    if current_user.rol == 'lector' and not current_user.puede_renombrar_archivos():
        flash("No tienes permisos para renombrar archivos.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    print("🚩 ¡Llegué a la función renombrar_archivo!")

    archivo_nombre_actual = request.form.get("archivo_nombre_actual")
    carpeta_actual = request.form.get("carpeta_actual")
    usuario_id = request.form.get("usuario_id")
    nuevo_nombre = request.form.get("nuevo_nombre")

    # --- Normalización robusta de path ---
    def join_dropbox_path(parent, name):
        if not parent or parent in ('/', '', None):
            return f"/{name}"
        return f"{parent.rstrip('/')}/{name}"

    old_path = join_dropbox_path(carpeta_actual, archivo_nombre_actual)
    new_path = join_dropbox_path(carpeta_actual, nuevo_nombre)

    # --- Log antes de buscar archivo ---
    print("DEBUG | archivo_nombre_actual:", archivo_nombre_actual)
    print("DEBUG | carpeta_actual:", carpeta_actual)
    print("DEBUG | usuario_id:", usuario_id)
    print("DEBUG | nuevo_nombre:", nuevo_nombre)
    print("DEBUG | old_path:", old_path)
    print("DEBUG | new_path:", new_path)
    all_paths = [a.dropbox_path for a in Archivo.query.all()]
    print("DEBUG | Paths en base:", all_paths)

    if not (archivo_nombre_actual and carpeta_actual and usuario_id and nuevo_nombre):
        print("DEBUG | Faltan datos para renombrar")
        flash("Faltan datos para renombrar.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    archivo = Archivo.query.filter_by(dropbox_path=old_path).first()
    if not archivo:
        print(f"DEBUG | Archivo no encontrado en la base para path: {old_path}")
        flash("Archivo no encontrado en la base de datos.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
    try:
        print(f"DEBUG | Renombrando en Dropbox: {old_path} -> {new_path}")
        dbx.files_move_v2(old_path, new_path, allow_shared_folder=True, autorename=True)
    except Exception as e:
        print(f"DEBUG | Error renombrando en Dropbox: {e}")
        flash(f"Error renombrando en Dropbox: {e}", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    archivo.nombre = nuevo_nombre
    archivo.dropbox_path = new_path
    db.session.commit()

    # Registrar actividad
    current_user.registrar_actividad('file_renamed', f'Archivo renombrado de "{archivo_nombre_actual}" a "{nuevo_nombre}"')

    print(f"DEBUG | Renombrado exitoso: {old_path} -> {new_path}")
    flash("Archivo renombrado correctamente.", "success")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))


def sincronizar_dropbox_a_bd():
    print("🚩 Iniciando sincronización de Dropbox a BD...")
    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])

    # Obtén todos los paths que ya tienes en la base para comparar rápido
    paths_existentes = set([a.dropbox_path for a in Archivo.query.all()])
    print(f"DEBUG | Archivos existentes en BD: {len(paths_existentes)}")
    
    nuevos = 0
    total_archivos = 0
    
    # Obtener todos los usuarios para mapear emails a IDs
    usuarios = User.query.all()
    usuarios_por_email = {u.email: u.id for u in usuarios}
    print(f"DEBUG | Usuarios encontrados: {list(usuarios_por_email.keys())}")

    # Buscar archivos en cada carpeta de usuario
    for usuario in usuarios:
        if not usuario.dropbox_folder_path:
            print(f"DEBUG | Usuario {usuario.email} no tiene dropbox_folder_path")
            continue
            
        print(f"DEBUG | Sincronizando archivos de usuario: {usuario.email}")
        print(f"DEBUG | Path del usuario: {usuario.dropbox_folder_path}")
        
        try:
            # Listar archivos del usuario en Dropbox
            res = dbx.files_list_folder(usuario.dropbox_folder_path, recursive=True)
            print(f"DEBUG | Encontrados {len(res.entries)} elementos para {usuario.email}")
            
            for entry in res.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    total_archivos += 1
                    dropbox_path = entry.path_display
                    
                    if dropbox_path in paths_existentes:
                        continue  # Ya está sincronizado

                    print(f"DEBUG | Nuevo archivo encontrado: {dropbox_path}")
                    
                    # Extraer información del path
                    partes = dropbox_path.strip("/").split("/")
                    
                    # Determina categoría y subcategoría si existen
                    categoria = ""
                    subcategoria = ""
                    
                    if len(partes) > 2:
                        categoria = partes[2]  # Después del email y carpeta raíz
                    if len(partes) > 3:
                        subcategoria = partes[3]

                    nuevo_archivo = Archivo(
                        nombre=entry.name,
                        categoria=categoria,
                        subcategoria=subcategoria,
                        dropbox_path=dropbox_path,
                        usuario_id=usuario.id
                    )
                    db.session.add(nuevo_archivo)
                    nuevos += 1
                    print(f"DEBUG | Agregado a BD: {entry.name} -> {dropbox_path}")
                    
        except Exception as e:
            print(f"ERROR | Error sincronizando usuario {usuario.email}: {e}")
            continue

    db.session.commit()
    print(f"🚩 Sincronización completa: {nuevos} archivos nuevos de {total_archivos} totales")
    print(f"DEBUG | Total de archivos en BD después de sincronización: {Archivo.query.count()}")

@bp.route("/sincronizar_dropbox")
def sincronizar_dropbox():
    print("🚩 Iniciando sincronización completa...")
    try:
        sincronizar_dropbox_a_bd()
        sincronizar_carpetas_dropbox()
        flash("¡Sincronización completada!", "success")
    except Exception as e:
        print(f"ERROR | Error en sincronización: {e}")
        flash(f"Error en sincronización: {e}", "error")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route("/verificar_bd")
def verificar_bd():
    """Verifica el estado de la base de datos y muestra información útil"""
    print("🔍 Verificando estado de la base de datos...")
    
    # Contar archivos en BD
    total_archivos = Archivo.query.count()
    print(f"DEBUG | Total de archivos en BD: {total_archivos}")
    
    # Mostrar algunos archivos de ejemplo
    archivos_ejemplo = Archivo.query.limit(10).all()
    print("DEBUG | Ejemplos de archivos en BD:")
    for archivo in archivos_ejemplo:
        print(f"DEBUG | - {archivo.nombre} -> {archivo.dropbox_path} (Usuario: {archivo.usuario_id})")
    
    # Contar usuarios
    total_usuarios = User.query.count()
    print(f"DEBUG | Total de usuarios: {total_usuarios}")
    
    # Mostrar usuarios con sus carpetas de Dropbox
    usuarios = User.query.all()
    print("DEBUG | Usuarios y sus carpetas de Dropbox:")
    for usuario in usuarios:
        print(f"DEBUG | - {usuario.email} -> {usuario.dropbox_folder_path}")
    
    flash(f"Base de datos verificada. {total_archivos} archivos, {total_usuarios} usuarios.", "info")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route("/sincronizar_usuario/<email>")
def sincronizar_usuario(email):
    """Sincroniza archivos de un usuario específico"""
    print(f"🔄 Sincronizando archivos del usuario: {email}")
    
    try:
        # Buscar el usuario
        usuario = User.query.filter_by(email=email).first()
        if not usuario:
            print(f"ERROR | Usuario {email} no encontrado en la BD")
            flash(f"Usuario {email} no encontrado", "error")
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
        print(f"DEBUG | Usuario encontrado: {usuario.email} (ID: {usuario.id})")
        
        # Verificar si tiene carpeta de Dropbox configurada
        if not usuario.dropbox_folder_path:
            print(f"DEBUG | Usuario {email} no tiene dropbox_folder_path configurado")
            # Intentar usar el email como carpeta
            usuario.dropbox_folder_path = f"/{email}"
            db.session.commit()
            print(f"DEBUG | Configurado dropbox_folder_path: {usuario.dropbox_folder_path}")
        
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        
        # Obtener todos los archivos del usuario en Dropbox
        print(f"DEBUG | Buscando archivos en: {usuario.dropbox_folder_path}")
        res = dbx.files_list_folder(usuario.dropbox_folder_path, recursive=True)
        print(f"DEBUG | Encontrados {len(res.entries)} elementos para {email}")
        
        archivos_procesados = 0
        archivos_nuevos = 0
        archivos_existentes = 0
        
        for entry in res.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                archivos_procesados += 1
                dropbox_path = entry.path_display
                
                print(f"DEBUG | Procesando archivo: {entry.name} -> {dropbox_path}")
                
                # Verificar si ya existe en la BD
                archivo_existente = Archivo.query.filter_by(dropbox_path=dropbox_path).first()
                if archivo_existente:
                    print(f"DEBUG | Archivo ya existe en BD: {archivo_existente.nombre}")
                    archivos_existentes += 1
                else:
                    print(f"DEBUG | Archivo nuevo, agregando a BD: {entry.name}")
                    
                    # Extraer información del path
                    partes = dropbox_path.strip("/").split("/")
                    categoria = ""
                    subcategoria = ""
                    
                    if len(partes) > 2:
                        categoria = partes[2]  # Después del email
                    if len(partes) > 3:
                        subcategoria = partes[3]
                    
                    nuevo_archivo = Archivo(
                        nombre=entry.name,
                        categoria=categoria,
                        subcategoria=subcategoria,
                        dropbox_path=dropbox_path,
                        usuario_id=usuario.id
                    )
                    db.session.add(nuevo_archivo)
                    archivos_nuevos += 1
                    print(f"DEBUG | Archivo agregado: {entry.name} -> {dropbox_path}")
        
        db.session.commit()
        print(f"🔄 Sincronización completada para {email}:")
        print(f"DEBUG | - Archivos procesados: {archivos_procesados}")
        print(f"DEBUG | - Archivos existentes: {archivos_existentes}")
        print(f"DEBUG | - Archivos nuevos: {archivos_nuevos}")
        
        flash(f"Sincronización completada para {email}. {archivos_nuevos} archivos nuevos agregados.", "success")
        
    except Exception as e:
        print(f"ERROR | Error sincronizando usuario {email}: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error sincronizando usuario: {e}", "error")
    
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route("/verificar_dropbox")
def verificar_dropbox():
    """Verifica el estado de Dropbox y muestra información útil"""
    print("🔍 Verificando estado de Dropbox...")
    
    try:
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        
        # Verificar conexión
        account = dbx.users_get_current_account()
        print(f"DEBUG | Conectado a Dropbox como: {account.email}")
        
        # Listar archivos en la raíz
        res = dbx.files_list_folder(path="", recursive=False, limit=10)
        print(f"DEBUG | Archivos en raíz de Dropbox: {len(res.entries)}")
        
        for entry in res.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                print(f"DEBUG | Archivo: {entry.name} -> {entry.path_display}")
            elif isinstance(entry, dropbox.files.FolderMetadata):
                print(f"DEBUG | Carpeta: {entry.name} -> {entry.path_display}")
        
        # Verificar usuarios en BD
        usuarios = User.query.all()
        print(f"DEBUG | Usuarios en BD: {len(usuarios)}")
        
        for usuario in usuarios:
            if usuario.dropbox_folder_path:
                print(f"DEBUG | Usuario {usuario.email} tiene carpeta: {usuario.dropbox_folder_path}")
                try:
                    user_res = dbx.files_list_folder(path=usuario.dropbox_folder_path, recursive=False, limit=5)
                    print(f"DEBUG | - Contenido: {len(user_res.entries)} elementos")
                    for entry in user_res.entries[:3]:  # Solo mostrar los primeros 3
                        print(f"DEBUG | - {entry.name}")
                except Exception as e:
                    print(f"DEBUG | - Error accediendo a carpeta: {e}")
            else:
                print(f"DEBUG | Usuario {usuario.email} NO tiene carpeta de Dropbox configurada")
        
        flash(f"Dropbox verificado. Conectado como: {account.email}", "info")
        
    except Exception as e:
        print(f"ERROR | Error verificando Dropbox: {e}")
        flash(f"Error verificando Dropbox: {e}", "error")
    
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route("/buscar_archivo_especifico")
def buscar_archivo_especifico():
    """Busca el archivo específico que está causando problemas"""
    print("🔍 Buscando archivo específico: DOCUMENTOS_FINANCIEROS_TITULAR_JOHAN.png")
    
    try:
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        
        # Buscar el archivo específico
        archivo_nombre = "DOCUMENTOS_FINANCIEROS_TITULAR_JOHAN.png"
        
        print(f"DEBUG | Estrategia 1: Búsqueda exacta")
        search_result = dbx.files_search_v2(query=archivo_nombre, path="", max_results=20)
        print(f"DEBUG | Búsqueda exacta encontrada: {len(search_result.matches)} resultados")
        
        archivo_encontrado = None
        
        for match in search_result.matches:
            if hasattr(match.metadata, 'path_display'):
                print(f"DEBUG | Archivo encontrado: {match.metadata.name} -> {match.metadata.path_display}")
                if match.metadata.name == archivo_nombre:
                    archivo_encontrado = match.metadata
                    print(f"DEBUG | ¡Archivo específico encontrado! {match.metadata.path_display}")
                    break
        
        if not archivo_encontrado:
            print(f"DEBUG | Estrategia 2: Buscar en la carpeta específica")
            try:
                # Buscar directamente en la carpeta donde sabemos que está
                path_especifico = "/johan@gmail.com/Documentos financieros/Recibo de pago"
                res = dbx.files_list_folder(path_especifico, recursive=False)
                print(f"DEBUG | Archivos en {path_especifico}: {len(res.entries)}")
                
                for entry in res.entries:
                    if isinstance(entry, dropbox.files.FileMetadata):
                        print(f"DEBUG | Archivo en carpeta: {entry.name} -> {entry.path_display}")
                        if entry.name == archivo_nombre:
                            archivo_encontrado = entry
                            print(f"DEBUG | ¡Archivo encontrado en carpeta específica! {entry.path_display}")
                            break
            except Exception as e:
                print(f"ERROR | Error buscando en carpeta específica: {e}")
        
        if archivo_encontrado:
            print(f"DEBUG | Procesando archivo encontrado: {archivo_encontrado.name}")
            
            # Verificar si ya existe en la BD
            archivo_existente = Archivo.query.filter_by(dropbox_path=archivo_encontrado.path_display).first()
            if archivo_existente:
                print(f"DEBUG | Archivo ya existe en BD: {archivo_existente.nombre} -> {archivo_existente.dropbox_path}")
                print(f"DEBUG | Usuario ID: {archivo_existente.usuario_id}")
                flash(f"Archivo '{archivo_encontrado.name}' ya existe en la base de datos.", "info")
            else:
                print(f"DEBUG | Archivo no existe en BD, agregando...")
                
                # Buscar usuario johan@gmail.com
                usuario = User.query.filter_by(email="johan@gmail.com").first()
                if not usuario:
                    print(f"ERROR | Usuario johan@gmail.com no encontrado")
                    flash("Usuario johan@gmail.com no encontrado", "error")
                    return redirect(url_for("listar_dropbox.carpetas_dropbox"))
                
                print(f"DEBUG | Usuario encontrado: {usuario.email} (ID: {usuario.id})")
                
                # Extraer información del path
                partes = archivo_encontrado.path_display.strip("/").split("/")
                print(f"DEBUG | Partes del path: {partes}")
                
                categoria = "Documentos financieros"
                subcategoria = "Recibo de pago"
                
                nuevo_archivo = Archivo(
                    nombre=archivo_encontrado.name,
                    categoria=categoria,
                    subcategoria=subcategoria,
                    dropbox_path=archivo_encontrado.path_display,
                    usuario_id=usuario.id
                )
                db.session.add(nuevo_archivo)
                db.session.commit()
                
                print(f"DEBUG | Archivo agregado exitosamente: {nuevo_archivo.nombre} -> {nuevo_archivo.dropbox_path}")
                flash(f"Archivo '{archivo_encontrado.name}' agregado a la base de datos.", "success")
        else:
            print(f"DEBUG | ❌ Archivo '{archivo_nombre}' no encontrado en Dropbox")
            flash(f"Archivo '{archivo_nombre}' no encontrado en Dropbox.", "error")
        
    except Exception as e:
        print(f"ERROR | Error buscando archivo específico: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error buscando archivo: {e}", "error")
    
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route("/buscar_archivo_dropbox/<nombre_archivo>")
def buscar_archivo_dropbox(nombre_archivo):
    """Busca un archivo específico en Dropbox y lo sincroniza"""
    print(f"🔍 Buscando archivo en Dropbox: {nombre_archivo}")
    
    try:
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        
        # Buscar el archivo en Dropbox con múltiples estrategias
        print(f"DEBUG | Estrategia 1: Búsqueda exacta por nombre")
        search_result = dbx.files_search_v2(query=nombre_archivo, path="", max_results=20)
        print(f"DEBUG | Búsqueda exacta encontrada: {len(search_result.matches)} resultados")
        
        archivos_encontrados = []
        archivo_principal = None
        
        # Revisar resultados exactos
        for match in search_result.matches:
            if hasattr(match.metadata, 'path_display'):
                print(f"DEBUG | Archivo encontrado: {match.metadata.name} -> {match.metadata.path_display}")
                archivos_encontrados.append({
                    'nombre': match.metadata.name,
                    'path': match.metadata.path_display,
                    'tipo': 'exacto'
                })
                
                # Si es el archivo que buscamos exactamente
                if match.metadata.name == nombre_archivo:
                    archivo_principal = match.metadata
                    print(f"DEBUG | ¡Archivo principal encontrado! {match.metadata.name}")
        
        # Si no se encontró con búsqueda exacta, intentar búsqueda parcial
        if not archivo_principal:
            print(f"DEBUG | Estrategia 2: Búsqueda parcial por nombre base")
            nombre_base = nombre_archivo.split('.')[0]  # Sin extensión
            search_result_parcial = dbx.files_search_v2(query=nombre_base, path="", max_results=50)
            print(f"DEBUG | Búsqueda parcial encontrada: {len(search_result_parcial.matches)} resultados")
            
            for match in search_result_parcial.matches:
                if hasattr(match.metadata, 'path_display'):
                    print(f"DEBUG | Archivo parcial: {match.metadata.name} -> {match.metadata.path_display}")
                    archivos_encontrados.append({
                        'nombre': match.metadata.name,
                        'path': match.metadata.path_display,
                        'tipo': 'parcial'
                    })
                    
                    # Si es el archivo que buscamos
                    if match.metadata.name == nombre_archivo:
                        archivo_principal = match.metadata
                        print(f"DEBUG | ¡Archivo principal encontrado en búsqueda parcial! {match.metadata.name}")
                        break
        
        # Si encontramos el archivo principal, agregarlo a la BD
        if archivo_principal:
            print(f"DEBUG | Procesando archivo principal: {archivo_principal.name}")
            
            # Verificar si ya existe en la BD
            archivo_existente = Archivo.query.filter_by(dropbox_path=archivo_principal.path_display).first()
            if archivo_existente:
                print(f"DEBUG | Archivo ya existe en BD: {archivo_existente.nombre} -> {archivo_existente.dropbox_path}")
                flash(f"Archivo '{archivo_principal.name}' ya existe en la base de datos.", "info")
            else:
                print(f"DEBUG | Agregando archivo a BD: {archivo_principal.name}")
                
                # Extraer información del path
                partes = archivo_principal.path_display.strip("/").split("/")
                usuario_id = None
                categoria = ""
                subcategoria = ""
                
                print(f"DEBUG | Partes del path: {partes}")
                
                if len(partes) > 0:
                    # Buscar usuario por email en el path
                    for parte in partes:
                        usuario = User.query.filter_by(email=parte).first()
                        if usuario:
                            usuario_id = usuario.id
                            print(f"DEBUG | Usuario encontrado: {usuario.email} (ID: {usuario.id})")
                            break
                
                if len(partes) > 1:
                    categoria = partes[1]
                if len(partes) > 2:
                    subcategoria = partes[2]
                
                nuevo_archivo = Archivo(
                    nombre=archivo_principal.name,
                    categoria=categoria,
                    subcategoria=subcategoria,
                    dropbox_path=archivo_principal.path_display,
                    usuario_id=usuario_id
                )
                db.session.add(nuevo_archivo)
                db.session.commit()
                
                print(f"DEBUG | Archivo agregado exitosamente: {nuevo_archivo.nombre} -> {nuevo_archivo.dropbox_path}")
                flash(f"Archivo '{archivo_principal.name}' agregado a la base de datos.", "success")
        else:
            print(f"DEBUG | ❌ Archivo '{nombre_archivo}' no encontrado en Dropbox")
            flash(f"Archivo '{nombre_archivo}' no encontrado en Dropbox.", "error")
        
        print(f"DEBUG | Búsqueda completada. {len(archivos_encontrados)} archivos encontrados en total")
        
    except Exception as e:
        print(f"ERROR | Error buscando archivo en Dropbox: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error buscando archivo: {e}", "error")
    
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route("/sincronizar_dropbox_completo")
def sincronizar_dropbox_completo():
    """Sincronización alternativa que busca desde la raíz de Dropbox"""
    print("🚩 Iniciando sincronización completa desde raíz...")
    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
    
    try:
        # Buscar desde la raíz
        res = dbx.files_list_folder(path="", recursive=True)
        print(f"DEBUG | Encontrados {len(res.entries)} elementos en Dropbox")
        
        # Obtener archivos existentes
        paths_existentes = set([a.dropbox_path for a in Archivo.query.all()])
        print(f"DEBUG | Archivos existentes en BD: {len(paths_existentes)}")
        
        nuevos = 0
        archivos_procesados = 0
        
        for entry in res.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                archivos_procesados += 1
                dropbox_path = entry.path_display
                
                if dropbox_path in paths_existentes:
                    continue
                
                print(f"DEBUG | Nuevo archivo: {dropbox_path}")
                
                # Intentar encontrar usuario basado en el path
                partes = dropbox_path.strip("/").split("/")
                usuario_id = None
                
                if len(partes) > 0:
                    # Buscar usuario por email en el path
                    for parte in partes:
                        usuario = User.query.filter_by(email=parte).first()
                        if usuario:
                            usuario_id = usuario.id
                            break
                
                # Extraer categoría y subcategoría
                categoria = ""
                subcategoria = ""
                if len(partes) > 1:
                    categoria = partes[1]
                if len(partes) > 2:
                    subcategoria = partes[2]
                
                nuevo_archivo = Archivo(
                    nombre=entry.name,
                    categoria=categoria,
                    subcategoria=subcategoria,
                    dropbox_path=dropbox_path,
                    usuario_id=usuario_id
                )
                db.session.add(nuevo_archivo)
                nuevos += 1
                print(f"DEBUG | Agregado: {entry.name} -> {dropbox_path}")
        
        db.session.commit()
        print(f"🚩 Sincronización completa: {nuevos} archivos nuevos de {archivos_procesados} procesados")
        flash(f"¡Sincronización completa! {nuevos} archivos nuevos agregados.", "success")
        
    except Exception as e:
        print(f"ERROR | Error en sincronización completa: {e}")
        flash(f"Error en sincronización: {e}", "error")
    
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

def sincronizar_carpetas_dropbox():
    """Sincroniza carpetas de Dropbox que no están en la base de datos"""
    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
    
    # Obtener todas las carpetas que ya están en la base de datos
    carpetas_existentes = set([f.dropbox_path for f in Folder.query.all()])
    
    # Obtener todos los usuarios
    usuarios = User.query.all()
    usuarios_por_email = {u.email: u for u in usuarios}
    
    nuevos = 0
    
    for usuario in usuarios:
        if not usuario.dropbox_folder_path:
            continue
            
        try:
            # Listar carpetas del usuario en Dropbox
            res = dbx.files_list_folder(usuario.dropbox_folder_path, recursive=True)
            
            for entry in res.entries:
                if isinstance(entry, dropbox.files.FolderMetadata):
                    dropbox_path = entry.path_display
                    
                    # Si la carpeta no está en la base de datos, agregarla
                    if dropbox_path not in carpetas_existentes:
                        # Extraer nombre de la carpeta del path
                        nombre = entry.name
                        
                        nueva_carpeta = Folder(
                            name=nombre,
                            user_id=usuario.id,
                            dropbox_path=dropbox_path,
                            es_publica=True  # Por defecto las carpetas existentes son públicas
                        )
                        db.session.add(nueva_carpeta)
                        nuevos += 1
                        print(f"Nueva carpeta agregada: {dropbox_path}")
                        
        except dropbox.exceptions.ApiError as e:
            print(f"Error accediendo a carpeta de {usuario.email}: {e}")
            continue
    
    db.session.commit()
    print(f"Sincronización de carpetas completada: {nuevos} carpetas nuevas agregadas a la base de datos.")

@bp.route("/subir_archivo_rapido", methods=["POST"])
def subir_archivo_rapido():
    """Endpoint para subir archivos directamente a una carpeta específica sin categorías"""
    from app.models import User, Beneficiario, Archivo
    import json

    # Verificar permisos del lector
    if current_user.rol == 'lector' and not current_user.puede_modificar_archivos():
        flash("No tienes permisos para subir archivos.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    print("POST: Procesando subida rápida de archivo")
    
    # Obtener datos del formulario
    usuario_id = request.form.get("usuario_id")
    carpeta_destino = request.form.get("carpeta_destino")
    archivo = request.files.get("archivo")
    
    print("usuario_id recibido:", usuario_id)
    print("carpeta_destino recibida:", carpeta_destino)
    print("Archivo recibido:", archivo.filename if archivo else None)

    # Validar campos obligatorios
    if not (usuario_id and carpeta_destino and archivo):
        print("ERROR: Faltan campos obligatorios")
        flash("Completa todos los campos obligatorios", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    # Validar y obtener usuario/beneficiario
    usuario = None
    try:
        if usuario_id.startswith("user-"):
            real_id = int(usuario_id[5:])
            usuario = User.query.get(real_id)
            print(f"Es titular (User), id extraído: {real_id}")
        elif usuario_id.startswith("beneficiario-"):
            real_id = int(usuario_id[13:])
            usuario = Beneficiario.query.get(real_id)
            print(f"Es beneficiario, id extraído: {real_id}")
        else:
            print(f"usuario_id inválido: '{usuario_id}' (no tiene prefijo válido)")
            flash("Formato de usuario inválido. Debe seleccionar un usuario del formulario.", "error")
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    except (ValueError, IndexError) as e:
        print(f"Error al procesar usuario_id: {e}")
        flash("Error al procesar el usuario seleccionado", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    if not usuario:
        print("ERROR: Usuario no encontrado o inválido")
        flash("Usuario no encontrado en la base de datos", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    # Leer el archivo una sola vez
    archivo_content = archivo.read()
    archivo.seek(0)  # Resetear el puntero del archivo para futuras lecturas

    try:
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        
        # Verificar que la carpeta destino existe, si no, crearla
        try:
            dbx.files_get_metadata(carpeta_destino)
            print(f"Carpeta destino ya existe: {carpeta_destino}")
        except dropbox.exceptions.ApiError as e:
            if "not_found" in str(e):
                print(f"Creando carpeta destino: {carpeta_destino}")
                dbx.files_create_folder_v2(carpeta_destino)
            else:
                raise e

        # Subir archivo directamente a la carpeta destino
        dropbox_dest = f"{carpeta_destino}/{archivo.filename}"
        dbx.files_upload(archivo_content, dropbox_dest, mode=dropbox.files.WriteMode("overwrite"))
        print("Archivo subido exitosamente a Dropbox:", dropbox_dest)

        # Guardar en la base de datos con categoría y subcategoría genéricas
        nuevo_archivo = Archivo(
            nombre=archivo.filename,
            categoria="Subida Rápida",  # Categoría genérica
            subcategoria="Directo",     # Subcategoría genérica
            dropbox_path=dropbox_dest,
            usuario_id=getattr(usuario, "id", None)
        )
        db.session.add(nuevo_archivo)
        db.session.commit()
        print("Archivo registrado en la base de datos con ID:", nuevo_archivo.id)

        # Registrar actividad
        current_user.registrar_actividad('file_uploaded', f'Archivo "{archivo.filename}" subido a Subida Rápida/Directo')

        # Redirección correcta según si es AJAX o no
        redirect_url = url_for("listar_dropbox.carpetas_dropbox")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": True, "redirectUrl": redirect_url})
        else:
            flash("Archivo subido exitosamente a la carpeta seleccionada.", "success")
            return redirect(redirect_url)

    except Exception as e:
        print(f"ERROR general en subida rápida de archivo: {e}")
        db.session.rollback()
        flash(f"Error al subir archivo: {str(e)}", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route("/usuario/<int:usuario_id>/carpetas")
@login_required
def ver_usuario_carpetas(usuario_id):
    usuario = User.query.get_or_404(usuario_id)
    
    # Usar EXACTAMENTE la misma lógica que carpetas_dropbox
    try:
        estructuras_usuarios = {}
        
        # Verificar configuración de Dropbox
        api_key = current_app.config.get("DROPBOX_API_KEY")
        if not api_key:
            flash("Error: Configuración de Dropbox no disponible.", "error")
            return render_template("usuario_carpetas.html", 
                                 usuario=usuario,
                                 usuario_id=usuario.id,
                                 estructuras_usuarios={},
                                 estructuras_usuarios_json="{}",
                                 folders_por_ruta={},
                                 usuario_actual=current_user)
        
        dbx = dropbox.Dropbox(api_key)

        # Crear carpeta raíz si no existe
        if not usuario.dropbox_folder_path:
            usuario.dropbox_folder_path = f"/{usuario.email}"
            try:
                dbx.files_create_folder_v2(usuario.dropbox_folder_path)
            except dropbox.exceptions.ApiError as e:
                if "conflict" not in str(e):
                    raise e
            db.session.commit()

        path = usuario.dropbox_folder_path
        print(f"=== ver_usuario_carpetas DEBUG ===")
        print(f"Usuario ID: {usuario.id}")
        print(f"Usuario Email: {usuario.email}")
        print(f"Dropbox folder path: {path}")
        
        try:
            # Usar la función optimizada con recursión limitada para mejor rendimiento
            estructura = obtener_estructura_dropbox_optimizada(path=path, max_depth=5)
        except Exception as e:
            print(f"Error obteniendo estructura para usuario {usuario.email}: {e}")
            estructura = {"_subcarpetas": {}, "_archivos": []}
        
        # Control de permisos para ver carpetas (misma lógica que carpetas_dropbox)
        if current_user.rol == "cliente":
            if current_user.id != usuario.id:
                # Cliente intentando ver carpetas de otro cliente - no permitir
                print("❌ Cliente intentando ver carpetas de otro cliente")
                flash("No tienes permiso para ver estas carpetas.", "error")
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
            else:
                # Cliente viendo sus propias carpetas - mostrar todas
                print("✅ Cliente viendo sus propias carpetas - mostrar todas")
                pass
        elif current_user.rol == "lector":
            # Lector puede ver todas las carpetas de todos los usuarios
            print("✅ Lector - puede ver todas las carpetas")
            pass
        elif current_user.rol == "admin" or current_user.rol == "superadmin":
            # Admin puede ver todas las carpetas
            print("✅ Admin/Superadmin - puede ver todas las carpetas")
            pass
        else:
            # Otros roles - solo mostrar carpetas públicas
            print("⚠️ Otro rol - solo mostrar carpetas públicas")
            folders = Folder.query.filter_by(user_id=usuario.id, es_publica=True).all()
            rutas_visibles = set(f.dropbox_path for f in folders)
            estructura = filtra_arbol_por_rutas(estructura, rutas_visibles, path, usuario.email)
        
        # Guardar la estructura en el diccionario (misma lógica que carpetas_dropbox)
        estructuras_usuarios[usuario.id] = estructura
        
        # Carpetas de este usuario
        folders = Folder.query.filter_by(user_id=usuario.id).all()
        folders_por_ruta = {f.dropbox_path: f for f in folders}
        
        print(f"=== FINAL DEBUG ===")
        print(f"Estructura final: {estructura}")
        print(f"Número de carpetas final: {len(estructura.get('_subcarpetas', {}))}")
        print(f"Carpetas encontradas: {list(estructura.get('_subcarpetas', {}).keys())}")
        print(f"Estructuras usuarios: {estructuras_usuarios}")

        return render_template(
            "usuario_carpetas.html",
            usuario=usuario,
            usuario_id=usuario.id,
            estructuras_usuarios=estructuras_usuarios,
            estructuras_usuarios_json=json.dumps(estructuras_usuarios),
            folders_por_ruta=folders_por_ruta,
            usuario_actual=current_user
        )
        
    except Exception as e:
        print(f"Error general en ver_usuario_carpetas: {e}")
        flash(f"Error al cargar carpetas: {str(e)}", "error")
        return render_template("usuario_carpetas.html", 
                             usuario=usuario,
                             usuario_id=usuario.id,
                             estructuras_usuarios={},
                             estructuras_usuarios_json="{}",
                             folders_por_ruta={},
                             usuario_actual=current_user)

@bp.route('/eliminar_archivo', methods=['POST'])
@login_required
def eliminar_archivo():
    """Elimina un archivo de Dropbox y de la base de datos"""
    from app.models import Archivo
    
    # Verificar permisos del lector
    if current_user.rol == 'lector' and not current_user.puede_eliminar_archivos():
        flash("No tienes permisos para eliminar archivos.", "error")
        redirect_url = request.form.get("redirect_url", "")
        if redirect_url and "/usuario/" in redirect_url:
            return redirect(redirect_url)
        else:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    try:
        archivo_nombre = request.form.get("archivo_nombre")
        carpeta_actual = request.form.get("carpeta_actual")
        redirect_url = request.form.get("redirect_url", "")
        
        if not archivo_nombre or not carpeta_actual:
            flash("Faltan datos para eliminar el archivo.", "error")
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
        # Construir la ruta completa del archivo
        archivo_path = f"{carpeta_actual}/{archivo_nombre}".replace('//', '/')
        
        # Conectar a Dropbox
        dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])
        
        # Eliminar archivo de Dropbox
        try:
            dbx.files_delete_v2(archivo_path)
            print(f"DEBUG | Archivo eliminado de Dropbox: {archivo_path}")
        except dropbox.exceptions.ApiError as e:
            if "not_found" in str(e):
                print(f"DEBUG | Archivo no encontrado en Dropbox: {archivo_path}")
            else:
                raise e
        
        # Eliminar registro de la base de datos
        archivo_bd = Archivo.query.filter_by(dropbox_path=archivo_path).first()
        if archivo_bd:
            db.session.delete(archivo_bd)
            db.session.commit()
            print(f"DEBUG | Registro eliminado de BD: {archivo_bd.nombre}")
        
        # Registrar actividad
        current_user.registrar_actividad('file_deleted', f'Archivo "{archivo_nombre}" eliminado')
        
        flash("Archivo eliminado correctamente.", "success")
        
    except Exception as e:
        print(f"ERROR | Error eliminando archivo: {e}")
        flash(f"Error eliminando archivo: {e}", "error")
    
    # Redirigir a la URL apropiada
    if redirect_url and "/usuario/" in redirect_url:
        return redirect(redirect_url)
    else:
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))


