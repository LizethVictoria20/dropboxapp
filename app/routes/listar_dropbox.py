from flask import Blueprint, json, jsonify, render_template, current_app, request, redirect, url_for, flash
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
    estructuras_usuarios = {}
    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])

    # Determina qué usuarios cargar
    if current_user.rol == "admin":
        usuarios = User.query.all()
        # Admin ve todas las carpetas
        folders = Folder.query.all()
    else:
        # Solo el usuario actual (cliente ve solo sus carpetas públicas)
        usuarios = [current_user]
        folders = Folder.query.filter_by(user_id=current_user.id, es_publica=True).all()

    usuarios_dict = {u.id: u for u in usuarios}
    folders_por_ruta = {f.dropbox_path: f for f in folders}

    for user in usuarios:
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
        
        # Filtrar la estructura según los permisos del usuario
        if current_user.rol != "admin":
            # Para clientes, solo mostrar carpetas que estén en folders_por_ruta
            rutas_visibles = set(folders_por_ruta.keys())
            estructura = filtra_arbol_por_rutas(estructura, rutas_visibles, path, user.email)
        
        estructuras_usuarios[user.id] = estructura

   
    return render_template(
        "carpetas_dropbox.html",
        estructuras_usuarios=estructuras_usuarios,
        usuarios=usuarios_dict,
        usuario_actual=current_user,
        estructuras_usuarios_json=json.dumps(estructuras_usuarios),
        folders_por_ruta=folders_por_ruta,
    )

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


@bp.route("/crear_carpeta", methods=["POST"])
def crear_carpeta():
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
        titulares = User.query.all()
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

        flash("Archivo subido y registrado exitosamente.", "success")
        return redirect(url_for("listar_dropbox.subir_archivo"))

    except Exception as e:
        print(f"ERROR general en subida de archivo: {e}")
        db.session.rollback()
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
    flash("Archivo movido correctamente.", "success")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route('/mover_archivo_modal', methods=['POST'])
def mover_archivo_modal():
    archivo_nombre = request.form.get("archivo_nombre")
    carpeta_actual = request.form.get("carpeta_actual")
    nueva_carpeta = request.form.get("nueva_carpeta")

    old_dropbox_path = f"{carpeta_actual}/{archivo_nombre}".replace('//', '/')
    archivo = Archivo.query.filter_by(dropbox_path=old_dropbox_path).first()
    if not archivo:
        flash("Archivo no encontrado", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    if not nueva_carpeta or nueva_carpeta.strip() == "":
        flash("Debes seleccionar una carpeta de destino.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    nuevo_destino = f"{nueva_carpeta}/{archivo.nombre}"

    if archivo.dropbox_path == nuevo_destino:
        flash("El destino no puede ser igual al origen.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])

    # Asegura que exista la carpeta destino
    try:
        dbx.files_create_folder_v2(nueva_carpeta)
    except dropbox.exceptions.ApiError as e:
        if "conflict" not in str(e):
            raise e

    # Mueve el archivo en Dropbox
    try:
        dbx.files_move_v2(archivo.dropbox_path, nuevo_destino, allow_shared_folder=True, autorename=True)
    except dropbox.exceptions.ApiError as e:
        flash("No se pudo mover el archivo en Dropbox: " + str(e), "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    # Actualiza en BD
    archivo.dropbox_path = nuevo_destino
    db.session.commit()
    flash("Archivo movido correctamente.", "success")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))


@bp.route('/renombrar_archivo', methods=['POST'])
def renombrar_archivo():
    from app.models import Archivo
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

    print(f"DEBUG | Renombrado exitoso: {old_path} -> {new_path}")
    flash("Archivo renombrado correctamente.", "success")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))


def sincronizar_dropbox_a_bd():
    dbx = dropbox.Dropbox(current_app.config["DROPBOX_API_KEY"])

    # Empieza en la raíz (puedes pasar path de usuario para hacerlo individual)
    res = dbx.files_list_folder(path="", recursive=True)
    nuevos = 0

    # Obtén todos los paths que ya tienes en la base para comparar rápido
    paths_existentes = set([a.dropbox_path for a in Archivo.query.all()])

    for entry in res.entries:
        if isinstance(entry, dropbox.files.FileMetadata):
            dropbox_path = entry.path_display

            if dropbox_path in paths_existentes:
                continue  # Ya está sincronizado

            # Lógica para extraer usuario/carpeta/categoría/subcategoría según tu estructura
            # Ejemplo para estructura: /usuario/categoria/subcategoria/archivo
            partes = dropbox_path.strip("/").split("/")
            if len(partes) < 2:
                continue  # Ignora archivos fuera de estructura esperada

            # Determina usuario
            posible_email = partes[0]
            usuario = User.query.filter_by(email=posible_email).first()
            usuario_id = usuario.id if usuario else None

            # Determina categoría y subcategoría si existen
            categoria = partes[1] if len(partes) > 2 else ""
            subcategoria = partes[2] if len(partes) > 3 else ""

            nuevo_archivo = Archivo(
                nombre=entry.name,
                categoria=categoria,
                subcategoria=subcategoria,
                dropbox_path=dropbox_path,
                usuario_id=usuario_id
            )
            db.session.add(nuevo_archivo)
            nuevos += 1

    db.session.commit()
    print(f"Sincronización completa: {nuevos} archivos nuevos agregados a la base de datos.")

@bp.route("/sincronizar_dropbox")
def sincronizar_dropbox():
    sincronizar_dropbox_a_bd()
    sincronizar_carpetas_dropbox()
    flash("¡Sincronización completada!", "success")
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

        flash("Archivo subido exitosamente a la carpeta seleccionada.", "success")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    except Exception as e:
        print(f"ERROR general en subida rápida de archivo: {e}")
        db.session.rollback()
        flash(f"Error al subir archivo: {str(e)}", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
