from flask import Blueprint, json, jsonify, render_template, current_app, request, redirect, url_for, flash
import json
from flask_login import current_user, login_required
from app.categorias import CATEGORIAS
import dropbox
from app.models import Archivo, Beneficiario, Folder, User, Notification, Comentario
from app import db
import unicodedata
from datetime import datetime
from app.dropbox_utils import get_dbx, get_valid_dropbox_token, with_base_folder, without_base_folder, sanitize_dropbox_segment, _normalize_dropbox_path
import time

bp = Blueprint("listar_dropbox", __name__)

# Caché simple en memoria para estructuras por usuario (TTL en segundos)
_estructuras_cache = {}
_CACHE_TTL_SECONDS = 60

def _get_cached_estructura(user_id):
    entry = _estructuras_cache.get(user_id)
    if not entry:
        return None
    ts, data = entry
    if (time.time() - ts) > _CACHE_TTL_SECONDS:
        # Expirado
        _estructuras_cache.pop(user_id, None)
        return None
    return data

def _set_cached_estructura(user_id, estructura):
    _estructuras_cache[user_id] = (time.time(), estructura)
@bp.route('/api/archivo/estado', methods=['GET'])
@login_required
def obtener_estado_archivo():
    """Obtiene el estado de un archivo por dropbox_path"""
    from app.models import Archivo
    dropbox_path = request.args.get('path')
    if dropbox_path:
        dropbox_path = str(dropbox_path).replace('//', '/').rstrip('/')
    if not dropbox_path:
        return jsonify({'success': False, 'error': 'Parámetro path requerido'}), 400
    archivo = Archivo.query.filter_by(dropbox_path=dropbox_path).first()
    estado = archivo.estado if archivo and archivo.estado else None
    es_publica = archivo.es_publica if archivo and hasattr(archivo, 'es_publica') else True
    return jsonify({'success': True, 'estado': estado, 'es_publica': es_publica})

@bp.route('/api/archivo/estado', methods=['POST'])
@login_required
def actualizar_estado_archivo():
    """Actualiza el estado de un archivo. Requiere permisos de admin/cliente o lector con permiso de modificar."""
    from app.models import Archivo, User
    data = request.get_json(silent=True) or {}
    dropbox_path = data.get('path')
    nuevo_estado = data.get('estado')
    if not dropbox_path or not nuevo_estado:
        return jsonify({'success': False, 'error': 'path y estado son requeridos'}), 400
    if nuevo_estado not in ['en_revision', 'validado', 'rechazado']:
        return jsonify({'success': False, 'error': 'Estado inválido'}), 400

    # Permisos: admin, cliente dueño, o lector con permiso de modificar
    if not current_user.is_authenticated or not hasattr(current_user, 'rol'):
        return jsonify({'success': False, 'error': 'No autorizado'}), 401

    # Normalizar path (evitar dobles //)
    dropbox_path = str(dropbox_path).replace('//', '/').rstrip('/')
    archivo = Archivo.query.filter_by(dropbox_path=dropbox_path).first()
    if not archivo:
        # Crear registro mínimo si no existe
        usuario_email = dropbox_path.strip('/').split('/')[0]
        user = User.query.filter_by(email=usuario_email).first()
        archivo = Archivo(  # type: ignore[call-arg]
            nombre=dropbox_path.split('/')[-1],
            categoria='',
            subcategoria='',
            dropbox_path=dropbox_path,
            usuario_id=user.id if user else None
        )
        db.session.add(archivo)

    # Si es cliente, solo puede cambiar estado de sus archivos
    if current_user.rol == 'cliente' and archivo.usuario_id and archivo.usuario_id != current_user.id:
        return jsonify({'success': False, 'error': 'Sin permisos para modificar este archivo'}), 403
    if current_user.rol == 'lector' and not current_user.puede_modificar_archivos():
        return jsonify({'success': False, 'error': 'Sin permisos'}), 403

    archivo.estado = nuevo_estado
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/api/mis-archivos', methods=['GET'])
@login_required
def api_mis_archivos():
    """Devuelve archivos del usuario actual con su estado"""
    try:
        query = Archivo.query.filter_by(usuario_id=current_user.id)
        # Si es cliente, ocultar archivos privados
        try:
            if hasattr(current_user, 'rol') and current_user.rol == 'cliente':
                query = query.filter(Archivo.es_publica.is_(True))
        except Exception:
            # Si no hay atributo rol, no aplicar filtro adicional
            pass

        archivos = query.order_by(Archivo.fecha_subida.desc()).limit(50).all()
        datos = []
        for a in archivos:
            datos.append({
                'id': a.id,
                'nombre': a.nombre,
                'categoria': a.categoria,
                'subcategoria': a.subcategoria,
                'estado': a.estado,
                'dropbox_path': a.dropbox_path,
                'es_publica': getattr(a, 'es_publica', True)
            })
        return jsonify({'success': True, 'archivos': datos})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def obtener_carpetas_dropbox_estructura(path="", dbx=None):
    if dbx is None:
        from app.dropbox_utils import get_dbx, with_base_folder, without_base_folder, sanitize_dropbox_segment
        dbx = get_dbx()
        res = dbx.files_list_folder(with_base_folder(path), recursive=True)
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
        from app.dropbox_utils import get_dbx
        try:
            dbx = get_dbx()
        except Exception as e:
            print(f"Warning: Error obteniendo cliente Dropbox: {e}")
            return {"_subcarpetas": {}, "_archivos": []}
    
    try:
        # Obtener contenido del directorio actual (no recursivo)
        res = dbx.files_list_folder(with_base_folder(path), recursive=False)
    except dropbox.exceptions.ApiError as e:
        print(f"Error accediendo a Dropbox path '{path}': {e}")
        # Retornar estructura vacía si el path no existe
        return {"_subcarpetas": {}, "_archivos": []}
    
    estructura = {"_subcarpetas": {}, "_archivos": []}

    for entry in res.entries:
        if isinstance(entry, dropbox.files.FolderMetadata):
            # Es una carpeta - explorar recursivamente
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
    
    if dbx is None:
        from app.dropbox_utils import get_dbx
        try:
            dbx = get_dbx()
        except Exception as e:
            print(f"Warning: Error obteniendo cliente Dropbox: {e}")
            return {"_subcarpetas": {}, "_archivos": []}
    
    # Limitar la profundidad para evitar recursión infinita
    if current_depth >= max_depth:
        return {"_subcarpetas": {}, "_archivos": []}
    
    try:
        # Si el path está vacío, usar la raíz de Dropbox
        if not path or path == "":
            path = ""
        
        res = dbx.files_list_folder(with_base_folder(path), recursive=False)

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
            estructura["_archivos"].append(entry.name)

    return estructura

def obtener_estructura_dropbox_recursiva_limitada(path="", dbx=None, max_depth=3, max_entries=10000):
    """
    Obtiene la estructura usando UNA llamada recursiva a Dropbox y limita por profundidad.
    Esto reduce dramáticamente el número de llamadas a la API comparado con listar por nivel.

    - path: ruta base a listar
    - max_depth: profundidad máxima relativa a path
    - max_entries: límite de elementos a procesar para evitar respuestas excesivas
    """
    if dbx is None:
        from app.dropbox_utils import get_dbx
        try:
            dbx = get_dbx()
        except Exception as e:
            print(f"Warning: Error obteniendo cliente Dropbox: {e}")
            return {"_subcarpetas": {}, "_archivos": []}

    base = without_base_folder((path or "")).rstrip("/")
    try:
        result = dbx.files_list_folder(with_base_folder(base if base != "/" else ""), recursive=True)
    except dropbox.exceptions.ApiError as e:
        print(f"Error accediendo a Dropbox path '{path}': {e}")
        # Si el path no existe, intentar crear la carpeta base del usuario y reintentar
        try:
            if isinstance(e.error, dropbox.files.ListFolderError) and getattr(e.error, 'is_path', lambda: False)():
                if hasattr(e.error.get_path(), 'is_not_found') and e.error.get_path().is_not_found():
                    usuario_email = base.strip('/').split('/')[0] if base else None
                    if usuario_email:
                        try:
                            from app.dropbox_utils import create_dropbox_folder
                            created = create_dropbox_folder(f"/{usuario_email}")
                            if created:
                                # Reintentar listado una vez
                                result = dbx.files_list_folder(with_base_folder(base if base != "/" else ""), recursive=True)
                            else:
                                return {"_subcarpetas": {}, "_archivos": []}
                        except Exception as ce:
                            print(f"No se pudo crear carpeta base del usuario {usuario_email}: {ce}")
                            return {"_subcarpetas": {}, "_archivos": []}
                    else:
                        return {"_subcarpetas": {}, "_archivos": []}
                else:
                    return {"_subcarpetas": {}, "_archivos": []}
            else:
                return {"_subcarpetas": {}, "_archivos": []}
        except Exception:
            return {"_subcarpetas": {}, "_archivos": []}

    # Función auxiliar para crear nodos anidados
    def ensure_path(root, parts):
        node = root
        for p in parts:
            node = node.setdefault("_subcarpetas", {}).setdefault(p, {"_subcarpetas": {}, "_archivos": []})
        return node

    estructura = {"_subcarpetas": {}, "_archivos": []}
    processed = 0

    def handle_entries(entries):
        nonlocal processed
        for entry in entries:
            if processed >= max_entries:
                break
            processed += 1

            if not getattr(entry, "path_display", None):
                continue

            full_path = without_base_folder(entry.path_display)
            if base and not full_path.startswith(base + "/") and full_path != base:
                continue

            rel = full_path[len(base):].lstrip("/") if base else full_path.lstrip("/")
            if not rel:
                continue
            parts = rel.split("/")
            depth = len(parts) - 1  # 0 = directo dentro de base

            if isinstance(entry, dropbox.files.FolderMetadata):
                if depth <= max_depth:
                    ensure_path(estructura, parts)
            elif isinstance(entry, dropbox.files.FileMetadata):
                if depth <= max_depth:
                    # Agregar archivo al nodo padre
                    parent_parts = parts[:-1]
                    file_name = parts[-1]
                    parent_node = ensure_path(estructura, parent_parts) if parent_parts else estructura
                    parent_node.setdefault("_archivos", []).append(file_name)

    handle_entries(result.entries)

    # Paginación: continuar mientras haya más resultados, respetando max_entries
    while getattr(result, "has_more", False) and processed < max_entries:
        result = dbx.files_list_folder_continue(result.cursor)
        handle_entries(result.entries)

    return estructura

def filtra_archivos_ocultos(estructura, usuario_id, prefix=""):
    """
    Filtra los archivos ocultos de la estructura basándose en la base de datos Y la ruta del usuario.
    SEGURIDAD: Solo muestra archivos dentro del dropbox_folder_path del usuario específico.
    - estructura: dict con formato {'_archivos': [...], '_subcarpetas': { ... }}
    - usuario_id: ID del usuario para filtrar archivos ocultos
    - prefix: path base actual para construir rutas completas
    """
    from app.models import Archivo, User
    
    if not estructura:
        return estructura
    
    nueva_estructura = {"_archivos": [], "_subcarpetas": {}}
    
    # SEGURIDAD: Obtener la ruta base del usuario para verificar que solo vea sus archivos
    usuario = User.query.get(usuario_id)
    if not usuario:
        print(f"DEBUG | Usuario {usuario_id} no encontrado para filtrar archivos, retornando estructura vacía")
        return nueva_estructura
    
    user_base_path = usuario.dropbox_folder_path
    if not user_base_path:
        user_base_path = f"/{usuario.email}"
        print(f"DEBUG | Usuario {usuario_id} sin dropbox_folder_path para archivos, usando email: {user_base_path}")
    
    # Normalizar rutas
    user_base_path = user_base_path.rstrip('/')
    prefix_normalized = prefix.rstrip('/')
    
    # VALIDACIÓN DE SEGURIDAD: Verificar que el prefix esté dentro de la ruta del usuario
    if not prefix_normalized.startswith(user_base_path):
        print(f"DEBUG | SEGURIDAD: Prefix {prefix_normalized} no está dentro de {user_base_path} para archivos, retornando vacío")
        return nueva_estructura
    
    # Obtener archivos del usuario en la BD y mapear por ruta
    archivos_visibles = Archivo.query.filter_by(usuario_id=usuario_id).all()
    rutas_visibles = {archivo.dropbox_path for archivo in archivos_visibles}
    path_a_archivo = {archivo.dropbox_path: archivo for archivo in archivos_visibles}
    
    # Importar usuario actual para aplicar reglas por rol
    from flask_login import current_user
    
    # Filtrar archivos: mostrar archivos que están en la BD O todos los archivos dentro de la ruta del usuario
    for archivo_nombre in estructura.get("_archivos", []):
        archivo_path = f"{prefix}/{archivo_nombre}".replace('//', '/')
        
        # VALIDACIÓN DE SEGURIDAD: Solo mostrar archivos dentro de la ruta del usuario
        if not archivo_path.startswith(user_base_path):
            print(f"DEBUG | SEGURIDAD: Archivo {archivo_path} no está dentro de {user_base_path}, saltando")
            continue
            
        # Decidir visibilidad según rol y bandera es_publica
        mostrar_archivo = False
        archivo_bd = path_a_archivo.get(archivo_path)

        # Roles admin/superadmin/lector: siempre pueden ver
        if hasattr(current_user, "rol") and current_user.rol in ["admin", "superadmin", "lector"]:
            mostrar_archivo = True
        else:
            # Rol cliente (u otros): si es el dueño, ocultar si es privado
            if hasattr(current_user, "rol") and current_user.rol == "cliente" and current_user.id == usuario_id:
                if archivo_bd is not None and getattr(archivo_bd, "es_publica", True) is False:
                    mostrar_archivo = False
                else:
                    # Si no está en BD o es pública, se muestra
                    mostrar_archivo = True
            else:
                # Por defecto, mantener la lógica anterior de pertenencia a la ruta/BD
                mostrar_archivo = (archivo_path in rutas_visibles or archivo_path.startswith(user_base_path))

        if mostrar_archivo:
            nueva_estructura["_archivos"].append(archivo_nombre)
            print(f"DEBUG | Archivo visible mostrado para usuario {usuario_id}: {archivo_nombre}")
        else:
            print(f"DEBUG | Archivo oculto filtrado para usuario {usuario_id}: {archivo_nombre} - {archivo_path}")
    
    # Procesar subcarpetas recursivamente
    for subcarpeta, contenido in estructura.get("_subcarpetas", {}).items():
        sub_prefix = f"{prefix}/{subcarpeta}".replace('//', '/')
        
        # VALIDACIÓN DE SEGURIDAD: Solo procesar subcarpetas dentro de la ruta del usuario
        if sub_prefix.startswith(user_base_path):
            nueva_estructura["_subcarpetas"][subcarpeta] = filtra_archivos_ocultos(
                contenido, usuario_id, sub_prefix
            )
        else:
            print(f"DEBUG | SEGURIDAD: Subcarpeta {sub_prefix} no está dentro de {user_base_path}, saltando")
    
    return nueva_estructura

def filtra_carpetas_ocultas(estructura, usuario_id, prefix=""):
    """
    Filtra las carpetas ocultas de la estructura basándose en la base de datos Y la ruta del usuario.
    SEGURIDAD: Solo muestra carpetas dentro del dropbox_folder_path del usuario específico.
    - estructura: dict con formato {'_archivos': [...], '_subcarpetas': { ... }}
    - usuario_id: ID del usuario para filtrar carpetas ocultas
    - prefix: path base actual para construir rutas completas
    """
    from app.models import Folder, User
    
    if not estructura:
        return estructura
    
    nueva_estructura = {"_archivos": [], "_subcarpetas": {}}
    
    # SEGURIDAD: Obtener la ruta base del usuario para verificar que solo vea sus carpetas
    usuario = User.query.get(usuario_id)
    if not usuario:
        print(f"DEBUG | Usuario {usuario_id} no encontrado, retornando estructura vacía")
        return nueva_estructura
    
    user_base_path = usuario.dropbox_folder_path
    if not user_base_path:
        user_base_path = f"/{usuario.email}"
        print(f"DEBUG | Usuario {usuario_id} sin dropbox_folder_path, usando email: {user_base_path}")
    
    # Normalizar rutas
    user_base_path = user_base_path.rstrip('/')
    prefix_normalized = prefix.rstrip('/')
    
    # VALIDACIÓN DE SEGURIDAD: Verificar que el prefix esté dentro de la ruta del usuario
    if not prefix_normalized.startswith(user_base_path):
        print(f"DEBUG | SEGURIDAD: Prefix {prefix_normalized} no está dentro de {user_base_path}, retornando vacío")
        return nueva_estructura
    
    # Obtener carpetas visibles del usuario en la BD
    carpetas_visibles = Folder.query.filter_by(user_id=usuario_id).all()
    rutas_visibles = {carpeta.dropbox_path for carpeta in carpetas_visibles}
    
    # Filtrar archivos: mostrar todos los archivos dentro de la ruta del usuario
    nueva_estructura["_archivos"] = estructura.get("_archivos", [])
    
    # Procesar subcarpetas recursivamente
    for subcarpeta, contenido in estructura.get("_subcarpetas", {}).items():
        sub_prefix = f"{prefix}/{subcarpeta}".replace('//', '/')
        carpeta_path = sub_prefix.replace('//', '/')
        
        # VALIDACIÓN DE SEGURIDAD: Solo procesar carpetas dentro de la ruta del usuario
        if not carpeta_path.startswith(user_base_path):
            print(f"DEBUG | SEGURIDAD: Carpeta {carpeta_path} no está dentro de {user_base_path}, saltando")
            continue
        
        # Mostrar la carpeta si:
        # 1. Está en la BD del usuario, O
        # 2. Tiene contenido (archivos o subcarpetas) Y está dentro de la ruta del usuario
        if carpeta_path in rutas_visibles or (contenido.get("_archivos") or contenido.get("_subcarpetas")):
            nueva_estructura["_subcarpetas"][subcarpeta] = filtra_carpetas_ocultas(
                contenido, usuario_id, sub_prefix
            )
            print(f"DEBUG | Carpeta visible mostrada para usuario {usuario_id}: {subcarpeta} - {carpeta_path}")
        else:
            print(f"DEBUG | Carpeta oculta filtrada para usuario {usuario_id}: {subcarpeta} - {carpeta_path}")
    
    return nueva_estructura

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
    # Verificar que el usuario esté autenticado antes de acceder a sus atributos
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        return redirect(url_for("auth.login"))
        
    try:
        estructuras_usuarios = {}
        
        # Verificar configuración de Dropbox
        api_key = get_valid_dropbox_token()
        if not api_key:
            return render_template("carpetas_dropbox.html", 
                                    estructuras_usuarios={},
                                    usuarios={},
                                    usuario_actual=current_user,
                                    estructuras_usuarios_json="{}",
                                    usuarios_emails_json="{}",
                                    folders_por_ruta={},
                                    config_error=True)
        
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
                    dbx.files_create_folder_v2(with_base_folder(user.dropbox_folder_path))
                except dropbox.exceptions.ApiError as e:
                    if "conflict" not in str(e):
                        raise e
                db.session.commit()

            path = user.dropbox_folder_path
            try:
                # Intentar caché por usuario para evitar recomputar en cada navegación
                estructura = _get_cached_estructura(user.id)
                if estructura is None:
                    # Profundidad según rol para optimizar
                    if current_user.rol in ["admin", "superadmin", "lector"]:
                        max_depth = 4
                    else:
                        max_depth = 3
                    # Obtener estructura en una sola pasada recursiva y guardar en caché
                    estructura = obtener_estructura_dropbox_recursiva_limitada(path=path, dbx=dbx, max_depth=max_depth)
                    _set_cached_estructura(user.id, estructura)
                
                # Filtrar archivos ocultos de la estructura para este usuario
                print(f"DEBUG | Filtrando archivos ocultos para usuario {user.id} en carpetas_dropbox")
                estructura = filtra_archivos_ocultos(estructura, user.id, path)
                
                # Filtrar carpetas ocultas de la estructura (exactamente como archivos)
                print(f"DEBUG | Filtrando carpetas ocultas para usuario {user.id} en carpetas_dropbox")
                estructura = filtra_carpetas_ocultas(estructura, user.id, path)
                
            except Exception as e:
                user_identifier = user.email if hasattr(user, 'email') else user.nombre
                print(f"Error obteniendo estructura para usuario {user_identifier}: {e}")
                estructura = {"_subcarpetas": {}, "_archivos": []}
            
            # Filtrar la estructura según los permisos del usuario
            if not current_user.is_authenticated or not hasattr(current_user, "rol"):
                return redirect(url_for("auth.login"))
            if current_user.rol == "cliente":
                # Para clientes, solo mostrar carpetas públicas
                print("🔧 Filtrando carpetas para cliente - solo mostrar públicas")
                # No aplicar filtra_arbol_por_rutas porque ya se aplicó filtra_carpetas_ocultas
                pass
            elif current_user.rol == "lector":
                # Para lectores, mostrar todas las carpetas sin filtrar
                # No aplicar filtra_arbol_por_rutas porque ya se aplicó filtra_carpetas_ocultas
                pass
            elif current_user.rol != "admin" and current_user.rol != "superadmin":
                # Para otros roles, solo mostrar carpetas públicas
                # No aplicar filtra_arbol_por_rutas porque ya se aplicó filtra_carpetas_ocultas
                pass
            
            estructuras_usuarios[user.id] = estructura

        # Crear un diccionario con los emails de los usuarios
        usuarios_emails = {}
        for user in usuarios:
            if hasattr(user, 'email'):
                usuarios_emails[user.id] = user.email
            else:
                # Para beneficiarios, usar el email del titular
                usuarios_emails[user.id] = user.titular.email if hasattr(user, 'titular') else str(user.id)
        
        # Asegurar que las claves de estructuras_usuarios sean strings para JSON
        estructuras_usuarios_json = json.dumps({
            str(uid): estructura for uid, estructura in estructuras_usuarios.items()
        })
        
        return render_template(
            "carpetas_dropbox.html",
            estructuras_usuarios=estructuras_usuarios,
            usuarios=usuarios_dict,
            usuario_actual=current_user,
            estructuras_usuarios_json=estructuras_usuarios_json,
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

@bp.route('/api/comentarios', methods=['GET'])
@login_required
def listar_comentarios():
    """Lista comentarios por dropbox_path (archivo o carpeta)."""
    path = request.args.get('path', '').strip()
    if not path:
        return jsonify({'success': False, 'error': 'Falta parámetro path'}), 400
    # Normalizar
    path = str(path).replace('//', '/').rstrip('/')
    # Por defecto, listar todos. Si el usuario es cliente, solo mostrar comentarios de admin/superadmin
    q = Comentario.query.filter_by(dropbox_path=path).order_by(Comentario.fecha_creacion.desc())
    try:
        if hasattr(current_user, 'rol') and current_user.rol == 'cliente':
            q = q.join(User, Comentario.user_id == User.id).filter(User.rol.in_(['admin', 'superadmin']))
    except Exception:
        pass
    comentarios = q.all()
    data = [
        {
            'id': c.id,
            'user_id': c.user_id,
            'usuario': getattr(c.usuario, 'email', str(c.user_id)),
            'contenido': c.contenido,
            'fecha_creacion': c.fecha_creacion.isoformat(timespec='seconds')
        } for c in comentarios
    ]
    return jsonify({'success': True, 'comentarios': data})

@bp.route('/api/comentarios', methods=['POST'])
@login_required
def crear_comentario():
    """Crea un comentario asociado a un dropbox_path."""
    # Solo admin o superadmin pueden crear comentarios
    if not hasattr(current_user, 'rol') or current_user.rol not in ['admin', 'superadmin']:
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    contenido = (data.get('contenido') or '').strip()
    tipo = (data.get('tipo') or 'archivo').strip()
    if not path or not contenido:
        return jsonify({'success': False, 'error': 'path y contenido son requeridos'}), 400
    if tipo not in ['archivo', 'carpeta']:
        tipo = 'archivo'
    # Normalizar
    path = str(path).replace('//', '/').rstrip('/')
    try:
        comentario = Comentario(
            user_id=current_user.id,
            dropbox_path=path,
            tipo=tipo,
            contenido=contenido,
        )
        db.session.add(comentario)
        db.session.commit()
        return jsonify({'success': True, 'id': comentario.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route("/api/carpeta_info/<path:ruta>")
@login_required
def obtener_info_carpeta(ruta):
    """Endpoint para obtener información de una carpeta específica"""
    from app.models import Folder
    
    # Verificar permisos del usuario actual
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        return jsonify({"error": "Sesión expirada"}), 401
    
    # Buscar la carpeta en la base de datos
    carpeta = Folder.query.filter_by(dropbox_path=f"/{ruta}").first()
    
    # Aplicar filtro de permisos según el rol
    if carpeta:
        # Verificar si el usuario actual puede ver esta carpeta
        puede_ver = False
        
        if current_user.rol == "cliente":
            # Cliente solo puede ver carpetas públicas de su cuenta
            puede_ver = carpeta.es_publica and carpeta.user_id == current_user.id
        elif current_user.rol == "lector":
            # Lector puede ver todas las carpetas
            puede_ver = True
        elif current_user.rol == "admin" or current_user.rol == "superadmin":
            # Admin puede ver todas las carpetas
            puede_ver = True
        else:
            # Otros roles solo pueden ver carpetas públicas
            puede_ver = carpeta.es_publica
        
        if puede_ver:
            return jsonify({
                'existe': True,
                'es_publica': carpeta.es_publica,
                'nombre': carpeta.name,
                'usuario_id': carpeta.user_id
            })
        else:
            # Carpeta existe pero no tiene permisos para verla
            return jsonify({
                'existe': False,
                'es_publica': True,  # Por defecto pública si no tiene permisos
                'nombre': ruta.split('/')[-1] if '/' in ruta else ruta,
                'usuario_id': None
            })
    else:
        return jsonify({
            'existe': False,
            'es_publica': True,  # Por defecto pública si no existe en BD
            'nombre': ruta.split('/')[-1] if '/' in ruta else ruta,
            'usuario_id': None
        })

@bp.route("/api/toggle_visibilidad", methods=["POST"])
@login_required
def toggle_visibilidad():
    """Cambia la visibilidad (pública/privada) de una carpeta o archivo.
    Espera JSON: { tipo: 'carpeta'|'archivo', ruta: '/email/...', es_publica: true|false, usuario_id: <int> }
    """
    from app.models import Folder, Archivo, User
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        return jsonify({"success": False, "error": "Sesión expirada"}), 401

    data = request.get_json(silent=True) or {}
    tipo = (data.get("tipo") or "").strip()
    ruta = (data.get("ruta") or "").strip()
    es_publica = data.get("es_publica")

    if tipo not in ("carpeta", "archivo"):
        return jsonify({"success": False, "error": "Tipo inválido"}), 400
    if not ruta:
        return jsonify({"success": False, "error": "Ruta requerida"}), 400
    if es_publica is None:
        return jsonify({"success": False, "error": "es_publica requerido"}), 400

    # Permisos: admin/superadmin o lector con permiso de modificar
    if not (
        current_user.rol in ["admin", "superadmin"] or
        (current_user.rol == "lector" and hasattr(current_user, 'puede_modificar_archivos') and current_user.puede_modificar_archivos())
    ):
        return jsonify({"success": False, "error": "No autorizado"}), 403

    # Normalizar ruta
    ruta_norm = str(ruta).replace('//', '/').rstrip('/')
    if not ruta_norm.startswith('/'):
        ruta_norm = '/' + ruta_norm

    try:
        if tipo == "carpeta":
            carpeta = Folder.query.filter_by(dropbox_path=ruta_norm).first()
            if not carpeta:
                # Crear registro de carpeta si no existe en BD
                partes = ruta_norm.strip('/').split('/')
                if not partes:
                    return jsonify({"success": False, "error": "Ruta inválida"}), 400
                usuario_email = partes[0]
                usuario = User.query.filter_by(email=usuario_email).first()
                if not usuario:
                    return jsonify({"success": False, "error": "Usuario no encontrado para la ruta"}), 404
                nombre_carpeta = partes[-1]
                carpeta = Folder(  # type: ignore[call-arg]
                    name=nombre_carpeta,
                    user_id=usuario.id,
                    dropbox_path=ruta_norm,
                    es_publica=bool(es_publica)
                )
                db.session.add(carpeta)
            else:
                carpeta.es_publica = bool(es_publica)
            # Propagar visibilidad a archivos dentro de la carpeta
            try:
                prefijo = ruta_norm.rstrip('/') + '/%'
                Archivo.query.filter(Archivo.dropbox_path.like(prefijo)).update({Archivo.es_publica: bool(es_publica)}, synchronize_session=False)
            except Exception as _:
                pass
            db.session.commit()
            return jsonify({"success": True, "tipo": "carpeta", "ruta": carpeta.dropbox_path, "es_publica": carpeta.es_publica})
        else:
            archivo = Archivo.query.filter_by(dropbox_path=ruta_norm).first()
            if not archivo:
                # Crear registro mínimo de archivo si no existe en BD
                partes = ruta_norm.strip('/').split('/')
                if not partes:
                    return jsonify({"success": False, "error": "Ruta inválida"}), 400
                usuario_email = partes[0]
                usuario = User.query.filter_by(email=usuario_email).first()
                nombre_archivo = partes[-1]
                archivo = Archivo(  # type: ignore[call-arg]
                    nombre=nombre_archivo,
                    categoria='',
                    subcategoria='',
                    dropbox_path=ruta_norm,
                    usuario_id=usuario.id if usuario else None,
                    es_publica=bool(es_publica)
                )
                db.session.add(archivo)
            else:
                archivo.es_publica = bool(es_publica)
            db.session.commit()
            return jsonify({"success": True, "tipo": "archivo", "ruta": archivo.dropbox_path, "es_publica": archivo.es_publica})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route("/api/carpeta_contenido/<path:ruta>")
@login_required
def obtener_contenido_carpeta(ruta):
    """Endpoint para obtener el contenido de una carpeta específica"""
    # Verificar que el usuario esté autenticado antes de acceder a sus atributos
    if not current_user.is_authenticated:
        return jsonify({"success": False, "error": "Debes iniciar sesión para acceder a esta función"}), 401
        
    print(f"API: Obteniendo contenido de carpeta: {ruta}")
    try:
        # Verificar permisos
        if not current_user.is_authenticated or not hasattr(current_user, "rol"):
            flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
            return redirect(url_for("auth.login"))
        
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
        dbx = get_dbx()
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
        if not current_user.is_authenticated or not hasattr(current_user, "rol"):
            flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
            return redirect(url_for("auth.login"))
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
@login_required
def crear_carpeta():
    # Verificar si es una petición AJAX
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    # Verificar que el usuario esté autenticado antes de acceder a sus atributos
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
        return redirect(url_for("auth.login"))
        
    # Verificar permisos del lector
    if current_user.rol == 'lector' and not current_user.puede_modificar_archivos():
        flash("No tienes permisos para crear carpetas.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    nombre = request.form.get("nombre")
    padre = request.form.get("padre", "")
    es_publica_raw = request.form.get("es_publica", "true")
    es_publica = es_publica_raw.lower() == "true"  # Por defecto pública
    
    print(f"🔧 Datos del formulario:")
    print(f"   - nombre: '{nombre}'")
    print(f"   - padre: '{padre}'")
    print(f"   - es_publica_raw: '{es_publica_raw}'")
    print(f"   - es_publica_boolean: {es_publica}")
    print(f"   - Todos los datos del formulario: {dict(request.form)}")
    print(f"🔧 Análisis de la ruta padre:")
    print(f"   - Tipo: {type(padre)}")
    print(f"   - Longitud: {len(padre) if padre else 0}")
    print(f"   - Contiene '/': {'/' in padre if padre else False}")
    print(f"   - Partes: {padre.split('/') if padre else []}")
    
    # Obtener el usuario_id específico del formulario
    usuario_id = request.form.get("usuario_id")
    if usuario_id:
        try:
            usuario_id = int(usuario_id)
            print(f"🔧 Usuario ID del formulario: {usuario_id}")
        except ValueError:
            print(f"❌ Error: usuario_id no es un número válido: {usuario_id}")
            usuario_id = current_user.id
    else:
        print(f"⚠️ No se encontró usuario_id en el formulario, usando current_user.id: {current_user.id}")
        usuario_id = current_user.id
    
    if not nombre:
        flash("El nombre de la carpeta es obligatorio.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    # Construir la ruta en Dropbox correctamente usando la misma lógica que renombrar_carpeta
    print(f"🔧 Procesando carpeta padre: '{padre}' para usuario {usuario_id}")
    
    # Obtener el usuario específico
    usuario_especifico = User.query.get(usuario_id)
    if not usuario_especifico:
        print(f"❌ Usuario {usuario_id} no encontrado")
        flash("Error: Usuario no encontrado.", "error")
        return redirect(url_for("listar_dropbox.ver_usuario_carpetas", usuario_id=usuario_id))
    
    # Construir la ruta base del usuario (misma lógica que renombrar_carpeta)
    if hasattr(usuario_especifico, 'dropbox_folder_path') and usuario_especifico.dropbox_folder_path:
        ruta_base = usuario_especifico.dropbox_folder_path
    else:
        # Fallback: usar el email del usuario
        ruta_base = f"/{usuario_especifico.email}"
        
    # Función auxiliar para construir rutas (misma que renombrar_carpeta)
    def join_dropbox_path(parent, name):
        if not parent or parent in ('/', '', None):
            return f"/{name}"
        return f"{parent.rstrip('/')}/{name}"
    
    if padre:
        # Limpiar la ruta padre
        padre = padre.strip().replace('//', '/')
        if padre.startswith('/'):
            padre = padre[1:]
        if padre.endswith('/'):
            padre = padre[:-1]
        
        
        if padre.startswith("/"):
            # Si la carpeta padre ya empieza con /, verificar si incluye la ruta base
            if padre.startswith(ruta_base):
                # Ya incluye la ruta base, usar directamente
                ruta = join_dropbox_path(padre, nombre)
            else:
                # No incluye la ruta base, agregarla
                carpeta_padre_completa = f"{ruta_base}{padre}"
                ruta = join_dropbox_path(carpeta_padre_completa, nombre)
        else:
            # Si no empieza con /, construir la ruta completa
            carpeta_padre_completa = f"{ruta_base}/{padre}"
            ruta = join_dropbox_path(carpeta_padre_completa, nombre)
        
    else:
        # Si no hay padre, crear en la carpeta del usuario específico
        ruta = join_dropbox_path(ruta_base, nombre)

    
    print(f"🔧 Creando carpeta: nombre='{nombre}', padre='{padre}', ruta='{ruta}'")
    print(f"🔧 Ruta final para crear en Dropbox: '{ruta}'")
    
    try:
        dbx = get_dbx()
        dbx.files_create_folder_v2(with_base_folder(ruta))
        
        # Guardar carpeta en la base de datos
        nueva_carpeta = Folder(  # type: ignore[call-arg]
            name=nombre,
            user_id=usuario_id,
            dropbox_path=ruta,
            es_publica=es_publica
        )
        db.session.add(nueva_carpeta)
        db.session.commit()

        # Registrar actividad
        current_user.registrar_actividad('folder_created', f'Carpeta "{nombre}" creada en {ruta}')
        
        tipo_carpeta = "pública" if es_publica else "privada"
        flash(f"Carpeta '{ruta}' creada correctamente como {tipo_carpeta}.", "success")
        
        # Crear notificación para el usuario específico
        crear_notificacion(
            usuario_id,
            "Carpeta Creada",
            f"La carpeta '{nombre}' ha sido creada exitosamente en {ruta}",
            "success"
        )
        
        # Si es una petición AJAX, retornar JSON
        if is_ajax:
            return jsonify({
                "success": True,
                "message": f"Carpeta '{ruta}' creada correctamente como {tipo_carpeta}.",
                "carpeta_path": ruta,
                "parent_path": padre,
                "redirect_url": url_for("listar_dropbox.ver_usuario_carpetas", usuario_id=usuario_id)
            })
        
    except dropbox.exceptions.ApiError as e:
        error_msg = f"Error creando carpeta: {e}"
        flash(error_msg, "error")
        # Crear notificación de error
        crear_notificacion(
            usuario_id,
            "Error al Crear Carpeta",
            f"Error creando carpeta '{nombre}': {e}",
            "error"
        )
        
        if is_ajax:
            return jsonify({"success": False, "error": error_msg}), 400
            
    except Exception as e:
        error_msg = f"Error guardando carpeta en base de datos: {e}"
        flash(error_msg, "error")
        # Crear notificación de error
        crear_notificacion(
            usuario_id,
            "Error al Crear Carpeta",
            f"Error guardando carpeta '{nombre}' en base de datos: {e}",
            "error"
        )
        
        if is_ajax:
            return jsonify({"success": False, "error": error_msg}), 500
        
    return redirect(url_for("listar_dropbox.ver_usuario_carpetas", usuario_id=usuario_id))

def normaliza(nombre):
    nfkd = unicodedata.normalize('NFKD', nombre or '')
    solo_ascii = u"".join([c for c in nfkd if not unicodedata.combining(c)])
    return solo_ascii.upper().strip().replace(" ", "_")

@bp.route("/subir_archivo", methods=["GET", "POST"])
@login_required
def subir_archivo():
    from app.models import User, Beneficiario, Archivo, Folder
    import json

    if request.method == "GET":
        print("GET: Mostrando formulario de subida")
        
        # Verificar que el usuario esté autenticado antes de acceder a sus atributos
        if not current_user.is_authenticated:
            flash("Debes iniciar sesión para acceder a esta función", "error")
            return redirect(url_for("auth.login"))
            
        # Filtrar usuarios según el rol del usuario actual
        if not current_user.is_authenticated or not hasattr(current_user, "rol"):
            flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
            return redirect(url_for("auth.login"))


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
    subcategoria = (request.form.get("subcategoria") or "").strip()
    archivo = request.files.get("archivo")
    
    print("usuario_id recibido:", usuario_id)
    print("Categoría recibida:", categoria)
    print("Subcategoría recibida:", subcategoria)
    print("Archivo recibido:", archivo.filename if archivo else None)

    # Validar campos obligatorios
    if not (usuario_id and categoria and archivo):
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

    # Verificar que el usuario esté autenticado antes de acceder a sus atributos
    if not current_user.is_authenticated:
        flash("Debes iniciar sesión para acceder a esta función", "error")
        return redirect(url_for("auth.login"))
        
    # Validación de seguridad: cliente solo puede subir a sus propias carpetas
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
        return redirect(url_for("auth.login"))
    
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
        # Obtener cliente Dropbox con manejo específico de errores de autenticación
        dbx = get_dbx()
        if dbx is None:
            print("ERROR: No se pudo obtener cliente de Dropbox - token inválido")
            flash("Error de autenticación con Dropbox. Los tokens han expirado. Contacta al administrador para reconfigurar la conexión.", "error")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "error": "Tokens de Dropbox expirados. Contacta al administrador."}), 401
            else:
                return redirect(url_for("listar_dropbox.subir_archivo"))
        
        # Carpeta raíz de usuario/beneficiario
        if hasattr(usuario, "dropbox_folder_path") and usuario.dropbox_folder_path:
            carpeta_usuario = usuario.dropbox_folder_path
            print("Carpeta raíz ya existe:", carpeta_usuario)
        else:
            # Determinar la ruta según el tipo de usuario
            if isinstance(usuario, User) and not getattr(usuario, "es_beneficiario", False):
                # TITULAR - usar su email
                carpeta_usuario = f"/{usuario.email}"
            elif isinstance(usuario, Beneficiario):
                # BENEFICIARIO - crear carpeta dentro del titular
                if hasattr(usuario, "titular") and usuario.titular:
                    # Asegurar que el titular tenga su carpeta raíz
                    if not usuario.titular.dropbox_folder_path:
                        usuario.titular.dropbox_folder_path = f"/{usuario.titular.email}"
                        try:
                            dbx.files_create_folder_v2(with_base_folder(usuario.titular.dropbox_folder_path))
                            print("Carpeta raíz del titular creada:", usuario.titular.dropbox_folder_path)
                        except dropbox.exceptions.ApiError as e:
                            if "conflict" not in str(e):
                                print("ERROR al crear carpeta raíz del titular:", e)
                                raise e
                        db.session.commit()
                    
                    # Crear carpeta del beneficiario dentro del titular
                    carpeta_usuario = f"{usuario.titular.dropbox_folder_path}/Beneficiarios/{usuario.nombre}"
                else:
                    # Fallback si no hay titular
                    carpeta_usuario = f"/{usuario.email}"
            else:
                # Usuario genérico
                carpeta_usuario = f"/{usuario.email}"
            
            print("Creando carpeta raíz para usuario:", carpeta_usuario)
            try:
                # Para beneficiarios, crear primero la carpeta "Beneficiarios" si no existe
                if isinstance(usuario, Beneficiario) and hasattr(usuario, "titular") and usuario.titular:
                    carpeta_beneficiarios = f"{usuario.titular.dropbox_folder_path}/Beneficiarios"
                    try:
                        dbx.files_create_folder_v2(with_base_folder(carpeta_beneficiarios))
                        print("Carpeta 'Beneficiarios' creada:", carpeta_beneficiarios)
                    except dropbox.exceptions.ApiError as e:
                        if "conflict" not in str(e):
                            print("ERROR al crear carpeta 'Beneficiarios':", e)
                            raise e
                        print("La carpeta 'Beneficiarios' ya existía")
                
                # Crear la carpeta del usuario/beneficiario
                dbx.files_create_folder_v2(with_base_folder(carpeta_usuario))
                print("Carpeta raíz creada en Dropbox:", carpeta_usuario)
            except dropbox.exceptions.ApiError as e:
                if "conflict" not in str(e):
                    print("ERROR al crear carpeta raíz en Dropbox:", e)
                    raise e
                print("La carpeta raíz ya existía en Dropbox")
            
            # Guardar ruta en la base de datos
            usuario.dropbox_folder_path = carpeta_usuario
            db.session.commit()
            print("Ruta raíz guardada en DB:", carpeta_usuario)

        # Crear carpeta de categoría únicamente
        categoria_saneada = sanitize_dropbox_segment(categoria)
        ruta_categoria = f"{carpeta_usuario}/{categoria_saneada}"
        try:
            dbx.files_create_folder_v2(with_base_folder(ruta_categoria))
            print("Carpeta categoría creada:", ruta_categoria)
            
            # Guardar carpeta categoría en la base de datos
            carpeta_cat = Folder(  # type: ignore[call-arg]
                name=categoria_saneada,
                user_id=getattr(usuario, "id", None),
                dropbox_path=ruta_categoria,
                es_publica=True
            )
            db.session.add(carpeta_cat)
            db.session.commit()  # Commit inmediato para asegurar que se guarde
            print("Carpeta categoría guardada en BD:", ruta_categoria)
            
        except dropbox.exceptions.ApiError as e:
            if "conflict" not in str(e):
                print("ERROR al crear carpeta categoría:", e)
                raise e
            print("La carpeta categoría ya existía:", ruta_categoria)
            
        # Subcategoría eliminada del flujo

        # Generar nombre final del archivo incluyendo nombre original y timestamp
        import time
        nombre_evidencia = categoria_saneada.upper().replace(" ", "_")
        nombre_original = archivo.filename
        nombre_base = nombre_original
        ext = ""
        if "." in nombre_original:
            nombre_base = nombre_original.rsplit(".", 1)[0]
            ext = "." + nombre_original.rsplit(".", 1)[1].lower()
        
        # Normalizar el nombre base del archivo
        nombre_base_normalizado = sanitize_dropbox_segment(nombre_base)
        
        # Generar timestamp único
        timestamp = str(int(time.time()))

        # Determinar tipo de usuario y generar nombre único
        if isinstance(usuario, User) and not getattr(usuario, "es_beneficiario", False):
            # TITULAR
            nombre_titular = sanitize_dropbox_segment(usuario.nombre or usuario.email.split('@')[0])
            nombre_final = f"TITULAR_{nombre_titular}_{nombre_base_normalizado}{ext}"
        elif isinstance(usuario, Beneficiario):
            # BENEFICIARIO
            nombre_ben = sanitize_dropbox_segment(usuario.nombre)
            if hasattr(usuario, "titular") and usuario.titular:
                nombre_titular = sanitize_dropbox_segment(usuario.titular.nombre)
            else:
                nombre_titular = "SIN_TITULAR"
            nombre_final = f"{nombre_ben}_TITULAR_{nombre_titular}_{nombre_base_normalizado}{ext}"
        else:
            # Usuario genérico
            nombre_final = f"{sanitize_dropbox_segment(usuario.nombre or usuario.email.split('@')[0])}_{nombre_base_normalizado}{ext}"

        print("DEBUG | Nombre final para guardar/subir:", nombre_final)

        # Subir archivo con nombre final (sin sobrescribir)
        dropbox_dest = f"{ruta_categoria}/{nombre_final}"
        try:
            dbx.files_upload(archivo_content, with_base_folder(dropbox_dest), mode=dropbox.files.WriteMode("add"))
        except dropbox.exceptions.ApiError as e:
            if "conflict" in str(e):
                # Si hay conflicto, agregar un sufijo adicional
                import random
                sufijo_random = str(random.randint(1000, 9999))
                nombre_sin_ext = nombre_final.rsplit(".", 1)[0] if "." in nombre_final else nombre_final
                ext_final = "." + nombre_final.rsplit(".", 1)[1] if "." in nombre_final else ""
                nombre_final = f"{nombre_sin_ext}_{sufijo_random}{ext_final}"
                dropbox_dest = f"{ruta_categoria}/{nombre_final}"
                dbx.files_upload(archivo_content, with_base_folder(dropbox_dest), mode=dropbox.files.WriteMode("add"))
            else:
                raise e
        print("Archivo subido exitosamente a Dropbox:", dropbox_dest)

        # Guardar en la base de datos
        # Guardar ruta lógica sin carpeta base
        dropbox_dest_logico = without_base_folder(dropbox_dest)
        nuevo_archivo = Archivo(  # type: ignore[call-arg]
            nombre=nombre_final,
            categoria=categoria,
            subcategoria="",
            dropbox_path=dropbox_dest_logico,
            usuario_id=getattr(usuario, "id", None),
            estado="en_revision"  # Automáticamente asignar "Pendiente para revisión"
        )
        db.session.add(nuevo_archivo)
        db.session.commit()
        # Invalidar caché de estructura para el usuario afectado
        try:
            afectado_id = getattr(usuario, "id", None)
            if afectado_id in _estructuras_cache:
                _estructuras_cache.pop(afectado_id, None)
        except Exception:
            pass
        print("Archivo registrado en la base de datos con ID:", nuevo_archivo.id)

        # Registrar actividad
        current_user.registrar_actividad('file_uploaded', f'Archivo "{archivo.filename}" subido a {categoria}')

        # Redirección correcta según si es AJAX o no
        redirect_url = url_for("listar_dropbox.carpetas_dropbox")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": True, "redirectUrl": redirect_url})
        else:
            flash("Archivo subido y registrado exitosamente.", "success")
            return redirect(redirect_url)


    except dropbox.exceptions.AuthError as e:
        db.session.rollback()
        print(f"ERROR de autenticación Dropbox: {e}")
        error_msg = "Tokens de Dropbox expirados o inválidos. Contacta al administrador para reconfigurar la conexión con Dropbox."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "error": error_msg}), 401
        else:
            flash(error_msg, "error")
            return redirect(url_for("listar_dropbox.subir_archivo"))
    
    except dropbox.exceptions.ApiError as e:
        db.session.rollback()
        print(f"ERROR API de Dropbox: {e}")
        if "invalid_access_token" in str(e) or "unauthorized" in str(e):
            error_msg = "Tokens de Dropbox expirados. Contacta al administrador para reconfigurar la conexión."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "error": error_msg}), 401
            else:
                flash(error_msg, "error")
                return redirect(url_for("listar_dropbox.subir_archivo"))
        else:
            error_msg = f"Error de Dropbox: {str(e)}"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "error": error_msg}), 500
            else:
                flash(error_msg, "error")
                return redirect(url_for("listar_dropbox.subir_archivo"))
    
    except Exception as e:
        db.session.rollback()
        print(f"ERROR general en subida de archivo: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "error": str(e)}), 500
        else:
            flash(f"Error al subir archivo: {str(e)}", "error")
            return redirect(url_for("listar_dropbox.subir_archivo"))

 

@bp.route('/mover_archivo/<archivo_nombre>/<path:carpeta_actual>', methods=['GET', 'POST'])
@login_required
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
    subcategoria = (request.form.get("subcategoria") or "").strip()
    usuario = User.query.get(usuario_id)
    if not usuario:
        flash("Selecciona un usuario válido.", "error")
        return redirect(url_for("listar_dropbox.mover_archivo", archivo_nombre=archivo_nombre, carpeta_actual=carpeta_actual))

    dbx = get_dbx()
    # Crear carpetas destino si no existen
    carpeta_usuario = usuario.dropbox_folder_path or f"/{usuario.email}"
    try:
        dbx.files_create_folder_v2(with_base_folder(carpeta_usuario))
    except dropbox.exceptions.ApiError as e:
        if "conflict" not in str(e):
            raise e
    usuario.dropbox_folder_path = carpeta_usuario
    db.session.commit()
    # Invalidar caché de estructura para el usuario afectado
    try:
        if usuario.id in _estructuras_cache:
            _estructuras_cache.pop(usuario.id, None)
    except Exception:
        pass
    ruta_categoria = f"{carpeta_usuario}/{categoria}"
    try:
        dbx.files_create_folder_v2(with_base_folder(ruta_categoria))
    except dropbox.exceptions.ApiError as e:
        if "conflict" not in str(e):
            raise e
    # Mover archivo en Dropbox a categoría (sin subcategoría)
    nuevo_destino = f"{ruta_categoria}/{archivo.nombre}"
    dbx.files_move_v2(with_base_folder(archivo.dropbox_path), with_base_folder(nuevo_destino), allow_shared_folder=True, autorename=True)

    # Actualiza en BD
    archivo.dropbox_path = nuevo_destino
    archivo.categoria = categoria
    archivo.subcategoria = ""
    archivo.usuario_id = usuario.id
    db.session.commit()
    
    # Registrar actividad
    current_user.registrar_actividad('file_moved', f'Archivo "{archivo_nombre}" movido a {categoria}')
    
    flash("Archivo movido correctamente.", "success")
    return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route('/exportar_archivos_carpeta', methods=['GET', 'POST'])
@login_required
def exportar_archivos_carpeta():
    """Exporta todos los archivos de una carpeta origen a una carpeta destino"""
    from app.models import Archivo
    
    # Verificar que el usuario esté autenticado y tenga permisos de admin
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
        return redirect(url_for("auth.login"))
    
    # Permitir exportaciones masivas a usuarios administrativos y clientes (para reorganizar sus archivos)
    if current_user.rol not in ["admin", "superadmin", "cliente"]:
        flash(f"No tienes permisos para realizar exportaciones masivas de archivos. Rol actual: {current_user.rol}", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    if request.method == 'GET':
        # Mostrar formulario para seleccionar carpetas origen y destino
        return render_template("exportar_archivos.html")
    
    # POST: procesar exportación
    carpeta_origen = request.form.get("carpeta_origen", "").strip()
    carpeta_destino = request.form.get("carpeta_destino", "").strip()
    
    if not carpeta_origen or not carpeta_destino:
        flash("Debes especificar tanto la carpeta origen como la carpeta destino.", "error")
        return redirect(url_for("listar_dropbox.exportar_archivos_carpeta"))
    
    # Normalizar rutas
    carpeta_origen = _normalize_dropbox_path(carpeta_origen)
    carpeta_destino = _normalize_dropbox_path(carpeta_destino)
    
    print(f"🔧 Exportando archivos de '{carpeta_origen}' a '{carpeta_destino}'")
    
    try:
        dbx = get_dbx()
        if not dbx:
            flash("Error: No se pudo conectar con Dropbox.", "error")
            return redirect(url_for("listar_dropbox.exportar_archivos_carpeta"))
        
        # Buscar todos los archivos en la carpeta origen en la base de datos
        archivos_a_exportar = []
        
        # Buscar archivos que coincidan con la carpeta origen
        if carpeta_origen.endswith('/'):
            carpeta_origen = carpeta_origen[:-1]
        
        archivos_db = Archivo.query.filter(
            Archivo.dropbox_path.like(f"{carpeta_origen}/%")
        ).all()
        
        print(f"🔧 Archivos encontrados en BD para carpeta '{carpeta_origen}': {len(archivos_db)}")
        
        if not archivos_db:
            # Buscar carpetas similares para sugerir al usuario
            todas_rutas = db.session.query(Archivo.dropbox_path).distinct().all()
            rutas_sugeridas = []
            
            for (ruta,) in todas_rutas:
                if "IOK" in ruta and "Cases" in ruta:
                    partes = ruta.strip('/').split('/')
                    if len(partes) >= 3:
                        ruta_base = '/' + '/'.join(partes[:3])
                        if ruta_base not in rutas_sugeridas:
                            rutas_sugeridas.append(ruta_base)
            
            mensaje = f"No se encontraron archivos en la carpeta '{carpeta_origen}'."
            if rutas_sugeridas:
                mensaje += f" Rutas disponibles: {', '.join(rutas_sugeridas[:3])}"
            
            flash(mensaje, "warning")
            return redirect(url_for("listar_dropbox.exportar_archivos_carpeta"))
        
        # Crear carpeta destino si no existe
        try:
            dbx.files_create_folder_v2(with_base_folder(carpeta_destino))
            print(f"🔧 Carpeta destino creada: {carpeta_destino}")
        except dropbox.exceptions.ApiError as e:
            if "conflict" not in str(e).lower():
                print(f"🔧 Error creando carpeta destino: {e}")
                raise e
            print(f"🔧 La carpeta destino ya existía: {carpeta_destino}")
        
        archivos_movidos = 0
        errores = []
        
        for archivo in archivos_db:
            try:
                # Construir nueva ruta manteniendo la estructura de subcarpetas
                ruta_relativa = archivo.dropbox_path[len(carpeta_origen):].lstrip('/')
                nueva_ruta = f"{carpeta_destino}/{ruta_relativa}"
                nueva_ruta = _normalize_dropbox_path(nueva_ruta)
                
                print(f"🔧 Moviendo: {archivo.dropbox_path} -> {nueva_ruta}")
                
                # Crear subcarpetas intermedias si es necesario
                subcarpeta_destino = '/'.join(nueva_ruta.split('/')[:-1])
                if subcarpeta_destino != carpeta_destino:
                    try:
                        dbx.files_create_folder_v2(with_base_folder(subcarpeta_destino))
                        print(f"🔧 Subcarpeta creada: {subcarpeta_destino}")
                    except dropbox.exceptions.ApiError as e:
                        if "conflict" not in str(e).lower():
                            print(f"🔧 Error creando subcarpeta: {e}")
                
                # Mover archivo en Dropbox
                result = dbx.files_move_v2(
                    with_base_folder(archivo.dropbox_path), 
                    with_base_folder(nueva_ruta), 
                    allow_shared_folder=True, 
                    autorename=True
                )
                
                # Obtener la ruta final en caso de que se haya renombrado
                ruta_final = without_base_folder(result.metadata.path_display or result.metadata.path_lower)
                
                # Actualizar registro en la base de datos
                archivo.dropbox_path = ruta_final
                db.session.commit()
                
                archivos_movidos += 1
                print(f"🔧 Archivo movido exitosamente: {archivo.nombre}")
                
            except Exception as e:
                error_msg = f"Error moviendo {archivo.nombre}: {str(e)}"
                errores.append(error_msg)
                print(f"🔧 {error_msg}")
                continue
        
        # Registrar actividad
        current_user.registrar_actividad('bulk_export', 
            f'Exportados {archivos_movidos} archivos de "{carpeta_origen}" a "{carpeta_destino}"')
        
        # Mostrar resultados
        if archivos_movidos > 0:
            flash(f"Exportación completada: {archivos_movidos} archivos movidos exitosamente.", "success")
        
        if errores:
            flash(f"Se encontraron {len(errores)} errores durante la exportación.", "warning")
            for error in errores[:5]:  # Mostrar solo los primeros 5 errores
                flash(error, "error")
            if len(errores) > 5:
                flash(f"... y {len(errores) - 5} errores más.", "error")
        
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
    except Exception as e:
        db.session.rollback()
        print(f"🔧 Error general en exportación: {e}")
        flash(f"Error durante la exportación: {str(e)}", "error")
        return redirect(url_for("listar_dropbox.exportar_archivos_carpeta"))

@bp.route('/mover_archivo_modal', methods=['POST'])
@login_required
def mover_archivo_modal():
    """Mueve un archivo de una carpeta a otra usando Dropbox API"""
    
    # Verificar que el usuario esté autenticado antes de acceder a sus atributos
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
        return redirect(url_for("auth.login"))
    
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
        usuario_id_form = request.form.get("usuario_id")  # Nuevo: obtener usuario_id del formulario
        
        print(f"DEBUG | Movimiento solicitado:")
        print(f"  Archivo: {archivo_nombre}")
        print(f"  Carpeta actual: {carpeta_actual}")
        print(f"  Nueva carpeta: {nueva_carpeta}")
        print(f"  Usuario ID del formulario: {usuario_id_form}")
        print(f"  Tipo nueva_carpeta: {type(nueva_carpeta)}")
        print(f"  Longitud nueva_carpeta: {len(nueva_carpeta) if nueva_carpeta else 'None'}")
        
        # Obtener la URL de redirección
        redirect_url = request.form.get("redirect_url", "")
        
        if not all([archivo_nombre, carpeta_actual, nueva_carpeta]):
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
        # Limpiar y normalizar la ruta de la nueva carpeta
        nueva_carpeta = nueva_carpeta.strip()
        if not nueva_carpeta.startswith('/'):
            nueva_carpeta = '/' + nueva_carpeta
        
        print(f"DEBUG | Nueva carpeta normalizada: '{nueva_carpeta}'")
        
        # DETERMINAR EL USUARIO CORRECTO PARA VALIDACIONES
        # Si viene de la ruta /usuario/id/carpetas, usar ese usuario específico
        # Si no, usar el usuario actual
        usuario_objetivo = None
        usuario_email_objetivo = None
        
        if usuario_id_form:
            try:
                usuario_objetivo = User.query.get(int(usuario_id_form))
                if usuario_objetivo:
                    usuario_email_objetivo = usuario_objetivo.email
                    print(f"DEBUG | Usando usuario específico del formulario:")
                    print(f"  Usuario ID: {usuario_objetivo.id}")
                    print(f"  Usuario email: {usuario_email_objetivo}")
                else:
                    print(f"DEBUG | Usuario ID {usuario_id_form} no encontrado, usando usuario actual")
                    usuario_email_objetivo = current_user.email
            except (ValueError, TypeError):
                print(f"DEBUG | Error al convertir usuario_id_form '{usuario_id_form}', usando usuario actual")
                usuario_email_objetivo = current_user.email
        else:
            usuario_email_objetivo = current_user.email
            print(f"DEBUG | No hay usuario_id_form, usando usuario actual: {usuario_email_objetivo}")
        
        # VALIDACIÓN: Verificar que el usuario solo pueda mover archivos entre sus propias carpetas
        usuario_email = usuario_email_objetivo
        print(f"DEBUG | Validación de permisos:")
        print(f"  Usuario email: {usuario_email}")
        print(f"  Carpeta actual: '{carpeta_actual}'")
        print(f"  Nueva carpeta: '{nueva_carpeta}'")
        print(f"  ¿Carpeta actual empieza con /{usuario_email}?: {carpeta_actual.startswith(f'/{usuario_email}') if carpeta_actual else 'None'}")
        print(f"  ¿Nueva carpeta empieza con /{usuario_email}?: {nueva_carpeta.startswith(f'/{usuario_email}')}")
        
        if usuario_email:
            # Verificar que la carpeta destino pertenece al usuario actual
            if not nueva_carpeta.startswith(f"/{usuario_email}"):
                flash(f"No puedes mover archivos a carpetas de otros usuarios. Solo puedes mover archivos entre tus propias carpetas.", "error")
                if redirect_url and "/usuario/" in redirect_url:
                    return redirect(redirect_url)
                else:
                    return redirect(url_for("listar_dropbox.carpetas_dropbox"))
            
            # Verificar que la carpeta origen también pertenece al usuario actual
            # Si la carpeta actual no empieza con el email del usuario, intentar construir la ruta completa
            carpeta_actual_completa = carpeta_actual
            if carpeta_actual and not carpeta_actual.startswith(f"/{usuario_email}"):
                # Si la carpeta actual es relativa, construir la ruta completa
                if carpeta_actual.startswith("/"):
                    carpeta_actual_completa = f"/{usuario_email}{carpeta_actual}"
                else:
                    carpeta_actual_completa = f"/{usuario_email}/{carpeta_actual}"
                
                print(f"DEBUG | Carpeta actual reconstruida: '{carpeta_actual_completa}'")
            
            # Verificar con la ruta completa
            if carpeta_actual and not carpeta_actual_completa.startswith(f"/{usuario_email}"):
                flash(f"No puedes mover archivos desde carpetas de otros usuarios.", "error")
                if redirect_url and "/usuario/" in redirect_url:
                    return redirect(redirect_url)
                else:
                    return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
        # Buscar archivo en Dropbox directamente (fuente de verdad)
        dbx = get_dbx()
        if dbx is None:
            flash("No hay conexión válida con Dropbox. Verifica las credenciales/tokens.", "error")
            return redirect(redirect_url or url_for("listar_dropbox.ver_usuario_carpetas", usuario_id=usuario_id_form or current_user.id))
        
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
        
        # Intentar construir la ruta del archivo directamente a partir del formulario
        try:
            # Usar la carpeta_actual ya reconstruida con email si aplica
            carpeta_base_para_archivo = carpeta_actual_completa or carpeta_actual or ''
            carpeta_base_para_archivo = _normalize_dropbox_path(carpeta_base_para_archivo)
            archivo_path_logico_intentado = _normalize_dropbox_path(f"{carpeta_base_para_archivo.rstrip('/')}/{archivo_nombre}")

            print(f"DEBUG | Intentando localizar archivo por ruta directa lógica: '{archivo_path_logico_intentado}'")
            try:
                archivo_path_api_directo = with_base_folder(archivo_path_logico_intentado)
                _ = dbx.files_get_metadata(archivo_path_api_directo)
                # Si no lanza excepción, la ruta existe
                archivo_encontrado = None
                archivo_path = archivo_path_api_directo
                print(f"DEBUG | Ruta directa válida (con base): {archivo_path}")
                # Log adicional para depurar from_path final que usaremos
                print(f"DEBUG | ORIGEN_RESUELTO_API: {archivo_path}")
                # === MOVER USANDO RUTA DIRECTA RESUELTA ===
                # Verificar que la carpeta destino existe
                print(f"DEBUG | Verificando existencia de carpeta destino: '{nueva_carpeta}'")
                try:
                    metadata_destino = dbx.files_get_metadata(with_base_folder(nueva_carpeta))
                    if not isinstance(metadata_destino, dropbox.files.FolderMetadata):
                        flash(f"El destino '{nueva_carpeta}' no es una carpeta válida", "error")
                        return redirect(redirect_url or url_for("listar_dropbox.carpetas_dropbox"))
                except Exception as e:
                    print(f"ERROR | Error verificando carpeta destino '{nueva_carpeta}': {e}")
                    flash(f"Error verificando carpeta destino '{nueva_carpeta}': {str(e)}", "error")
                    return redirect(redirect_url or url_for("listar_dropbox.carpetas_dropbox"))

                # Construir paths lógicos y finales para API
                archivo_path_logico = without_base_folder(archivo_path)
                new_dropbox_path_logico = _normalize_dropbox_path(f"{nueva_carpeta.rstrip('/')}/{archivo_nombre}")
                from_path_api = _normalize_dropbox_path(with_base_folder(archivo_path_logico))
                to_path_api = _normalize_dropbox_path(with_base_folder(new_dropbox_path_logico))

                print(f"DEBUG | Moviendo archivo en Dropbox (rama directa)...")
                print(f"  Desde (lógico): {archivo_path_logico}")
                print(f"  Hacia (lógico): {new_dropbox_path_logico}")
                print(f"  Desde (API): {from_path_api}")
                print(f"  Hacia (API): {to_path_api}")

                try:
                    # Confirmar existencia
                    dbx.files_get_metadata(from_path_api)
                except Exception as e_from:
                    print(f"ERROR | FROM no existe justo antes del move (rama directa): {from_path_api} -> {e_from}")
                
                result = dbx.files_move_v2(
                    from_path=from_path_api,
                    to_path=to_path_api,
                    allow_shared_folder=True,
                    autorename=True
                )

                # Path destino final
                if hasattr(result.metadata, 'path_display'):
                    result_path = result.metadata.path_display
                elif hasattr(result.metadata, 'path_lower'):
                    result_path = result.metadata.path_lower
                else:
                    result_path = str(result.metadata)

                print(f"DEBUG | Archivo movido exitosamente (rama directa): {result_path}")

                # Actualizar/crear registro BD
                archivo_bd = Archivo.query.filter_by(dropbox_path=archivo_path).first()
                if archivo_bd:
                    archivo_bd.dropbox_path = result_path
                else:
                    result_path_logico = without_base_folder(result_path)
                    parts = result_path_logico.strip('/').split('/')
                    usuario_email_res = parts[0] if len(parts) > 0 else ''
                    categoria = parts[1] if len(parts) > 1 else ''
                    subcategoria = parts[2] if len(parts) > 2 else ''
                    usuario_res = User.query.filter_by(email=usuario_email_res).first()
                    if usuario_res:
                        nuevo_archivo = Archivo(  # type: ignore[call-arg]
                            nombre=archivo_nombre,
                            dropbox_path=result_path_logico,
                            categoria=categoria,
                            subcategoria=subcategoria,
                            usuario_id=usuario_res.id,
                            estado="en_revision"
                        )
                        db.session.add(nuevo_archivo)
                db.session.commit()

                current_user.registrar_actividad('file_moved', f'Archivo "{archivo_nombre}" movido a {result_path}')
                flash(f"Archivo '{archivo_nombre}' movido exitosamente a '{nueva_carpeta}'", "success")

                return redirect(redirect_url or url_for("listar_dropbox.carpetas_dropbox"))
            except Exception as e_dir:
                print(f"DEBUG | Ruta directa no encontrada, se intentará búsqueda por nombre: {e_dir}")
                # Fallback: Buscar el archivo en Dropbox
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

                if not archivo_encontrado and search_result.matches:
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
        except Exception as e_loc:
            print(f"ERROR | Error intentando localizar archivo: {e_loc}")
            # Continuar con fallback normal
            
            # Verificar que la carpeta destino existe
            print(f"DEBUG | Verificando existencia de carpeta destino: '{nueva_carpeta}'")
            try:
                # Usar ruta completa con carpeta base configurada
                metadata_destino = dbx.files_get_metadata(with_base_folder(nueva_carpeta))
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
            
            # Obtener el path correcto del archivo encontrado (si no se resolvió por ruta directa)
            if 'archivo_path' not in locals() or not archivo_path:
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
            
            # Construir paths lógicos (sin carpeta base) y luego aplicar carpeta base
            archivo_path_logico = without_base_folder(archivo_path)
            new_dropbox_path_logico = _normalize_dropbox_path(f"{nueva_carpeta.rstrip('/')}/{archivo_nombre}")

            # Preparar paths finales para API
            from_path_api = _normalize_dropbox_path(with_base_folder(archivo_path_logico))
            to_path_api = _normalize_dropbox_path(with_base_folder(new_dropbox_path_logico))

            print(f"DEBUG | Moviendo archivo en Dropbox...")
            print(f"  Desde (lógico): {archivo_path_logico}")
            print(f"  Hacia (lógico): {new_dropbox_path_logico}")
            print(f"  Desde (API): {from_path_api}")
            print(f"  Hacia (API): {to_path_api}")
            # Confirmación de existencia justo antes del move
            try:
                dbx.files_get_metadata(from_path_api)
                print(f"DEBUG | Confirmado que existe FROM en Dropbox: {from_path_api}")
            except Exception as e_check:
                print(f"ERROR | FROM no existe justo antes del move: {from_path_api} -> {e_check}")

            # Validar existencia de origen; si no existe, probar con el path completo original
            try:
                dbx.files_get_metadata(from_path_api)
            except Exception as e_from_meta:
                print(f"WARN | from_path_api no existe: {e_from_meta}")
                # Si 'archivo_path' parece ser un path absoluto con base, probar con ese
                if isinstance(archivo_path, str) and archivo_path.startswith('/'):
                    try:
                        dbx.files_get_metadata(archivo_path)
                        print("DEBUG | Usando path original con base para 'from_path'")
                        from_path_api = _normalize_dropbox_path(archivo_path)
                    except Exception as e_from_orig:
                        print(f"ERROR | Tampoco existe path original con base: {e_from_orig}")

            result = dbx.files_move_v2(
                from_path=from_path_api,
                to_path=to_path_api,
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
                    # path en Dropbox real; convertir a lógico removiendo base
                    result_path_logico = without_base_folder(result_path)
                    path_parts = result_path_logico.strip('/').split('/')
                    usuario_email = path_parts[0]
                    categoria = path_parts[1] if len(path_parts) > 1 else ""
                    subcategoria = path_parts[2] if len(path_parts) > 2 else ""
                    
                    usuario = User.query.filter_by(email=usuario_email).first()
                    if usuario:
                        nuevo_archivo = Archivo(  # type: ignore[call-arg]
                            nombre=archivo_nombre,
                            dropbox_path=result_path_logico,
                            categoria=categoria,
                            subcategoria=subcategoria,
                            usuario_id=usuario.id,
                            estado="en_revision"  # Automáticamente asignar "Pendiente para revisión"
                        )
                        db.session.add(nuevo_archivo)
                        print(f"DEBUG | Nuevo registro creado en BD: {nuevo_archivo.nombre}")
            
            db.session.commit()
            print(f"DEBUG | Base de datos actualizada")
            
            # Registrar actividad
            current_user.registrar_actividad('file_moved', f'Archivo "{archivo_nombre}" movido de {archivo_path} a {result_path}')
            
            # Mostrar mensaje de éxito
            flash(f"Archivo '{archivo_nombre}' movido exitosamente a '{nueva_carpeta}'", "success")
            
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
@login_required
def renombrar_archivo():
    from app.models import Archivo, User, Beneficiario
    
    # Verificar que el usuario esté autenticado antes de acceder a sus atributos
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
        return redirect(url_for("auth.login"))
    
    # Verificar permisos del lector
    if current_user.rol == 'lector' and not current_user.puede_renombrar_archivos():
        flash("No tienes permisos para renombrar archivos.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    print("🚩 ¡Llegué a la función renombrar_archivo!")

    archivo_nombre_actual = request.form.get("archivo_nombre_actual")
    carpeta_actual = request.form.get("carpeta_actual")
    usuario_id = request.form.get("usuario_id")
    nuevo_nombre = request.form.get("nuevo_nombre")

    # Obtener el usuario para construir la ruta base
    try:
        usuario_id_int = int(usuario_id)
        usuario = User.query.get(usuario_id_int)
        if not usuario:
            # Intentar buscar como beneficiario
            usuario = Beneficiario.query.get(usuario_id_int)
        
        if not usuario:
            print(f"DEBUG | Usuario no encontrado con ID: {usuario_id}")
            flash("Usuario no encontrado.", "error")
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))
            
    except (ValueError, TypeError):
        print(f"DEBUG | usuario_id inválido: {usuario_id}")
        flash("ID de usuario inválido.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    # Construir la ruta base del usuario
    if hasattr(usuario, 'dropbox_folder_path') and usuario.dropbox_folder_path:
        # Si es un User, usar su dropbox_folder_path
        ruta_base = usuario.dropbox_folder_path
    elif hasattr(usuario, 'titular') and usuario.titular and usuario.titular.dropbox_folder_path:
        # Si es un Beneficiario, usar el dropbox_folder_path de su titular
        ruta_base = usuario.titular.dropbox_folder_path
    else:
        # Fallback: usar el email del usuario
        if hasattr(usuario, 'email'):
            ruta_base = f"/{usuario.email}"
        else:
            ruta_base = f"/{usuario.titular.email}" if hasattr(usuario, 'titular') else f"/usuario_{usuario.id}"

    # --- Normalización robusta de path ---
    def join_dropbox_path(parent, name):
        if not parent or parent in ('/', '', None):
            return f"/{name}"
        return f"{parent.rstrip('/')}/{name}"

    # Construir rutas completas incluyendo la ruta base del usuario
    if carpeta_actual.startswith("/"):
        # Si la carpeta actual ya empieza con /, verificar si incluye la ruta base
        if carpeta_actual.startswith(ruta_base):
            # Ya incluye la ruta base, usar directamente
            old_path = join_dropbox_path(carpeta_actual, archivo_nombre_actual)
            new_path = join_dropbox_path(carpeta_actual, nuevo_nombre)
        else:
            # No incluye la ruta base, agregarla
            carpeta_actual_completa = f"{ruta_base}{carpeta_actual}"
            old_path = join_dropbox_path(carpeta_actual_completa, archivo_nombre_actual)
            new_path = join_dropbox_path(carpeta_actual_completa, nuevo_nombre)
    else:
        # Si no empieza con /, construir la ruta completa
        carpeta_actual_completa = f"{ruta_base}/{carpeta_actual}"
        old_path = join_dropbox_path(carpeta_actual_completa, archivo_nombre_actual)
        new_path = join_dropbox_path(carpeta_actual_completa, nuevo_nombre)

    # --- Log antes de buscar archivo ---
    print("DEBUG | archivo_nombre_actual:", archivo_nombre_actual)
    print("DEBUG | carpeta_actual:", carpeta_actual)
    print("DEBUG | usuario_id:", usuario_id)
    print("DEBUG | nuevo_nombre:", nuevo_nombre)
    print("DEBUG | ruta_base:", ruta_base)
    print("DEBUG | old_path:", old_path)
    print("DEBUG | new_path:", new_path)
    all_paths = [a.dropbox_path for a in Archivo.query.all()]
    print("DEBUG | Paths en base:", all_paths)

    if not (archivo_nombre_actual and carpeta_actual and usuario_id and nuevo_nombre):
        print("DEBUG | Faltan datos para renombrar")
        
        # En caso de error, intentar redirigir al usuario específico si es posible
        try:
            usuario_id_int = int(usuario_id)
            return redirect(url_for("listar_dropbox.ver_usuario_carpetas", usuario_id=usuario_id_int))
        except:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    archivo = Archivo.query.filter_by(dropbox_path=old_path).first()
    if not archivo:
        print(f"DEBUG | Archivo no encontrado en la base para path: {old_path}")
        
        # En caso de error, intentar redirigir al usuario específico si es posible
        try:
            usuario_id_int = int(usuario_id)
            return redirect(url_for("listar_dropbox.ver_usuario_carpetas", usuario_id=usuario_id_int))
        except:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    dbx = get_dbx()
    try:
        print(f"DEBUG | Renombrando en Dropbox: {old_path} -> {new_path}")
        dbx.files_move_v2(with_base_folder(old_path), with_base_folder(new_path), allow_shared_folder=True, autorename=True)
    except Exception as e:
        print(f"DEBUG | Error renombrando en Dropbox: {e}")
        
        # En caso de error, intentar redirigir al usuario específico si es posible
        try:
            usuario_id_int = int(usuario_id)
            return redirect(url_for("listar_dropbox.ver_usuario_carpetas", usuario_id=usuario_id_int))
        except:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    archivo.nombre = nuevo_nombre
    archivo.dropbox_path = new_path
    db.session.commit()

    # Registrar actividad
    current_user.registrar_actividad('file_renamed', f'Archivo renombrado de "{archivo_nombre_actual}" a "{nuevo_nombre}"')

    print(f"DEBUG | Renombrado exitoso: {old_path} -> {new_path}")
    flash("Archivo renombrado correctamente.", "success")
    
    # Redirigir a la carpeta específica del usuario
    redirect_url = url_for("listar_dropbox.ver_usuario_carpetas", usuario_id=usuario_id_int)
    print(f"🔧 Redirigiendo a usuario específico: /usuario/{usuario_id_int}/carpetas")
    return redirect(redirect_url)


def sincronizar_dropbox_a_bd():
    print("🚩 Iniciando sincronización de Dropbox a BD...")
    dbx = get_dbx()

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

                    nuevo_archivo = Archivo(  # type: ignore[call-arg]
                        nombre=entry.name,
                        categoria=categoria,
                        subcategoria=subcategoria,
                        dropbox_path=without_base_folder(dropbox_path),
                        usuario_id=usuario.id,
                        estado="en_revision"  # Automáticamente asignar "Pendiente para revisión"
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
@login_required
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
@login_required
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
@login_required
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
        
        dbx = get_dbx()
        
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
                    
                    nuevo_archivo = Archivo(  # type: ignore[call-arg]
                        nombre=entry.name,
                        categoria=categoria,
                        subcategoria=subcategoria,
                        dropbox_path=without_base_folder(dropbox_path),
                        usuario_id=usuario.id,
                        estado="en_revision"  # Automáticamente asignar "Pendiente para revisión"
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
        dbx = get_dbx()
        
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
        dbx = get_dbx()
        
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
                
                nuevo_archivo = Archivo(  # type: ignore[call-arg]
                    nombre=archivo_encontrado.name,
                    categoria=categoria,
                    subcategoria=subcategoria,
                    dropbox_path=archivo_encontrado.path_display,
                    usuario_id=usuario.id,
                    estado="en_revision"  # Automáticamente asignar "Pendiente para revisión"
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
        dbx = get_dbx()
        
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
                
                nuevo_archivo = Archivo(  # type: ignore[call-arg]
                    nombre=archivo_principal.name,
                    categoria=categoria,
                    subcategoria=subcategoria,
                    dropbox_path=archivo_principal.path_display,
                    usuario_id=usuario_id,
                    estado="en_revision"  # Automáticamente asignar "Pendiente para revisión"
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
    dbx = get_dbx()
    
    try:
        # Buscar desde la raíz
        res = dbx.files_list_folder(path="", recursive=True)
        
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
                
                nuevo_archivo = Archivo(  # type: ignore[call-arg]
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
    dbx = get_dbx()
    
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
                        
                        nueva_carpeta = Folder(  # type: ignore[call-arg]
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
@login_required
def subir_archivo_rapido():
    """Endpoint para subir archivos directamente a una carpeta específica sin categorías"""
    from app.models import User, Beneficiario, Archivo
    import json

    # Verificar que el usuario esté autenticado antes de acceder a sus atributos
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
        return redirect(url_for("auth.login"))

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
            # Caso especial: usuario_id es un número directo (sin prefijo)
            try:
                real_id = int(usuario_id)
                # Intentar primero como User
                usuario = User.query.get(real_id)
                if usuario:
                    print(f"Es titular (User), id directo: {real_id}")
                else:
                    # Si no es User, intentar como Beneficiario
                    usuario = Beneficiario.query.get(real_id)
                    if usuario:
                        print(f"Es beneficiario, id directo: {real_id}")
                    else:
                        print(f"usuario_id no encontrado: {real_id}")
                        flash("Usuario no encontrado en la base de datos", "error")
                        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
            except ValueError:
                print(f"usuario_id inválido: '{usuario_id}' (no es un número válido)")
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
        dbx = get_dbx()
        
        # Construir la ruta completa usando el dropbox_folder_path del usuario
        if hasattr(usuario, 'dropbox_folder_path') and usuario.dropbox_folder_path:
            ruta_base = usuario.dropbox_folder_path
        else:
            # Determinar la ruta según el tipo de usuario y crearla si no existe
            if isinstance(usuario, User) and not getattr(usuario, "es_beneficiario", False):
                # TITULAR - usar su email
                ruta_base = f"/{usuario.email}"
                usuario.dropbox_folder_path = ruta_base
            elif isinstance(usuario, Beneficiario):
                # BENEFICIARIO - crear carpeta dentro del titular
                if hasattr(usuario, "titular") and usuario.titular:
                    # Asegurar que el titular tenga su carpeta raíz
                    if not usuario.titular.dropbox_folder_path:
                        usuario.titular.dropbox_folder_path = f"/{usuario.titular.email}"
                        try:
                            dbx.files_create_folder_v2(with_base_folder(usuario.titular.dropbox_folder_path))
                            print("Carpeta raíz del titular creada:", usuario.titular.dropbox_folder_path)
                        except dropbox.exceptions.ApiError as e:
                            if "conflict" not in str(e):
                                raise e
                        db.session.commit()
                    
                    # Crear carpeta del beneficiario dentro del titular
                    ruta_base = f"{usuario.titular.dropbox_folder_path}/Beneficiarios/{usuario.nombre}"
                    usuario.dropbox_folder_path = ruta_base
                else:
                    # Fallback si no hay titular
                    ruta_base = f"/{usuario.email}"
                    usuario.dropbox_folder_path = ruta_base
            else:
                # Usuario genérico
                ruta_base = f"/{usuario.email}" if hasattr(usuario, 'email') else f"/usuario_{usuario.id}"
                usuario.dropbox_folder_path = ruta_base
            
            # Crear la estructura de carpetas si no existe
            try:
                # Para beneficiarios, crear primero la carpeta "Beneficiarios" si no existe
                if isinstance(usuario, Beneficiario) and hasattr(usuario, "titular") and usuario.titular:
                    carpeta_beneficiarios = f"{usuario.titular.dropbox_folder_path}/Beneficiarios"
                    try:
                        dbx.files_create_folder_v2(with_base_folder(carpeta_beneficiarios))
                        print("Carpeta 'Beneficiarios' creada:", carpeta_beneficiarios)
                    except dropbox.exceptions.ApiError as e:
                        if "conflict" not in str(e):
                            raise e
                
                # Crear la carpeta del usuario/beneficiario
                dbx.files_create_folder_v2(with_base_folder(ruta_base))
                print("Carpeta raíz creada:", ruta_base)
            except dropbox.exceptions.ApiError as e:
                if "conflict" not in str(e):
                    raise e
                print("La carpeta raíz ya existía:", ruta_base)
            
            # Guardar en la base de datos
            db.session.commit()
            print("Ruta guardada en DB:", ruta_base)
        
        # Construir la ruta completa de destino
        if carpeta_destino.startswith("/"):
            # Si la carpeta destino ya empieza con /, verificar si incluye la ruta base del usuario
            if carpeta_destino.startswith(ruta_base):
                # Ya incluye la ruta base, usar directamente
                carpeta_destino_completa = carpeta_destino
                print(f"🔧 Carpeta destino ya incluye ruta base, usando directamente")
            else:
                # No incluye la ruta base, agregarla
                carpeta_destino_completa = f"{ruta_base}{carpeta_destino}"
                print(f"🔧 Carpeta destino no incluye ruta base, agregándola")
        else:
            # Si no empieza con /, construir la ruta completa
            carpeta_destino_completa = f"{ruta_base}/{carpeta_destino}"
            print(f"🔧 Construyendo ruta completa desde ruta relativa")
        
        print(f"🔧 Ruta base del usuario: {ruta_base}")
        print(f"🔧 Carpeta destino original: {carpeta_destino}")
        print(f"🔧 Carpeta destino completa: {carpeta_destino_completa}")
        print(f"🔧 Tipo de usuario: {type(usuario).__name__}")
        print(f"🔧 Usuario ID: {getattr(usuario, 'id', 'N/A')}")
        print(f"🔧 Usuario email: {getattr(usuario, 'email', 'N/A')}")
        
        # Verificar que la carpeta destino existe, si no, crearla
        try:
            dbx.files_get_metadata(carpeta_destino_completa)
            print(f"Carpeta destino ya existe: {carpeta_destino_completa}")
        except dropbox.exceptions.ApiError as e:
            if "not_found" in str(e):
                print(f"Creando carpeta destino: {carpeta_destino_completa}")
                dbx.files_create_folder_v2(with_base_folder(carpeta_destino_completa))
                
                # Guardar carpeta en la base de datos
                from app.models import Folder
                carpeta_nombre = carpeta_destino_completa.split('/')[-1]
                nueva_carpeta = Folder(  # type: ignore[call-arg]
                    name=carpeta_nombre,
                    user_id=getattr(usuario, "id", None),
                    dropbox_path=carpeta_destino_completa,
                    es_publica=True
                )
                db.session.add(nueva_carpeta)
                db.session.commit()
                print(f"Carpeta destino creada y registrada en BD: {carpeta_destino_completa}")
            else:
                raise e

        # Subir archivo directamente a la carpeta destino (sin sobrescribir)
        nombre_base = archivo.filename
        ext = ""
        if "." in archivo.filename:
            nombre_base = archivo.filename.rsplit(".", 1)[0]
            ext = "." + archivo.filename.rsplit(".", 1)[1].lower()
        
        nombre_normalizado = f"{normaliza(nombre_base)}{ext}"
        dropbox_dest = f"{carpeta_destino_completa}/{nombre_normalizado}"
        
        try:
            dbx.files_upload(archivo_content, with_base_folder(dropbox_dest), mode=dropbox.files.WriteMode("add"))
        except dropbox.exceptions.ApiError as e:
            if "conflict" in str(e):
                # Si hay conflicto, agregar un sufijo adicional
                import random
                sufijo_random = str(random.randint(1000, 9999))
                nombre_normalizado = f"{normaliza(nombre_base)}_{sufijo_random}{ext}"
                dropbox_dest = f"{carpeta_destino_completa}/{nombre_normalizado}"
                dbx.files_upload(archivo_content, with_base_folder(dropbox_dest), mode=dropbox.files.WriteMode("add"))
            else:
                raise e
        print("Archivo subido exitosamente a Dropbox:", dropbox_dest)

        # Guardar en la base de datos con categoría y subcategoría genéricas
        print(f"🔧 Guardando en BD con ruta: {dropbox_dest}")
        nuevo_archivo = Archivo(  # type: ignore[call-arg]
            nombre=nombre_normalizado,  # Usar el nombre normalizado sin timestamp
            categoria="Subida Rápida",  # Categoría genérica
            subcategoria="Directo",     # Subcategoría genérica
            dropbox_path=dropbox_dest,
            usuario_id=getattr(usuario, "id", None),
            estado="en_revision"  # Automáticamente asignar "Pendiente para revisión"
        )
        db.session.add(nuevo_archivo)
        db.session.commit()
        print("Archivo registrado en la base de datos con ID:", nuevo_archivo.id)

        # Registrar actividad
        current_user.registrar_actividad('file_uploaded', f'Archivo "{archivo.filename}" subido a Subida Rápida/Directo')

        # Redirección correcta según si es AJAX o no
        # Usar el usuario_id específico para redirigir a la carpeta del usuario
        usuario_id_redirect = getattr(usuario, "id", None)
        redirect_url = url_for("listar_dropbox.ver_usuario_carpetas", usuario_id=usuario_id_redirect)
        
        print(f"🔧 Redirigiendo a usuario específico: /usuario/{usuario_id_redirect}/carpetas")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": True, "redirectUrl": redirect_url})
        else:
            return redirect(redirect_url)

    except Exception as e:
        print(f"ERROR general en subida rápida de archivo: {e}")
        db.session.rollback()
        
        # En caso de error, intentar redirigir al usuario específico si es posible
        try:
            usuario_id_redirect = getattr(usuario, "id", None) if 'usuario' in locals() else None
            if usuario_id_redirect:
                return redirect(url_for("listar_dropbox.ver_usuario_carpetas", usuario_id=usuario_id_redirect))
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        except:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route("/usuario/<int:usuario_id>/carpetas")
@login_required
def ver_usuario_carpetas(usuario_id):
    # Verificar que el usuario esté autenticado antes de acceder a sus atributos
    if not current_user.is_authenticated:
        flash("Debes iniciar sesión para acceder a esta función", "error")
        return redirect(url_for("auth.login"))
        
    usuario = User.query.get_or_404(usuario_id)
    
    # Usar EXACTAMENTE la misma lógica que carpetas_dropbox
    try:
        estructuras_usuarios = {}
        
        # Verificar configuración de Dropbox
        api_key = get_valid_dropbox_token()
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
                dbx.files_create_folder_v2(with_base_folder(usuario.dropbox_folder_path))
            except dropbox.exceptions.ApiError as e:
                if "conflict" not in str(e):
                    raise e
            db.session.commit()

        path = usuario.dropbox_folder_path
        
        try:
            # Usar la función optimizada con recursión limitada para mejor rendimiento
            estructura = obtener_estructura_dropbox_optimizada(path=path, max_depth=5)
            
            # Filtrar archivos ocultos de la estructura
            print(f"DEBUG | Filtrando archivos ocultos para usuario {usuario.id}")
            estructura = filtra_archivos_ocultos(estructura, usuario.id, path)
            
            # Filtrar carpetas ocultas de la estructura (exactamente como archivos)
            print(f"DEBUG | Filtrando carpetas ocultas para usuario {usuario.id}")
            estructura = filtra_carpetas_ocultas(estructura, usuario.id, path)
            
        except Exception as e:
            print(f"Error obteniendo estructura para usuario {usuario.email}: {e}")
            estructura = {"_subcarpetas": {}, "_archivos": []}
        
        # Control de permisos para ver carpetas (misma lógica que carpetas_dropbox)
        if not current_user.is_authenticated or not hasattr(current_user, "rol"):
            flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
            return redirect(url_for("auth.login"))
        
        # Aplicar filtro de carpetas ocultas según el rol del usuario
        if current_user.rol == "cliente":
            if current_user.id != usuario.id:
                # Cliente intentando ver carpetas de otro cliente - no permitir
                print("❌ Cliente intentando ver carpetas de otro cliente")
                flash("No tienes permiso para ver estas carpetas.", "error")
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
            else:
                # Cliente viendo sus propias carpetas - solo mostrar públicas
                print("✅ Cliente viendo sus propias carpetas - solo mostrar públicas")
                # No aplicar filtra_arbol_por_rutas porque ya se aplicó filtra_carpetas_ocultas
                pass
        elif current_user.rol == "lector":
            # Lector puede ver todas las carpetas de todos los usuarios
            print("✅ Lector - puede ver todas las carpetas")
            # No aplicar filtra_arbol_por_rutas porque ya se aplicó filtra_carpetas_ocultas
            pass
        elif current_user.rol == "admin" or current_user.rol == "superadmin":
            # Admin puede ver todas las carpetas
            print("✅ Admin/Superadmin - puede ver todas las carpetas")
            # No aplicar filtra_arbol_por_rutas porque ya se aplicó filtra_carpetas_ocultas
            pass
        else:
            # Otros roles - solo mostrar carpetas públicas
            print("⚠️ Otro rol - solo mostrar carpetas públicas")
            # No aplicar filtra_arbol_por_rutas porque ya se aplicó filtra_carpetas_ocultas
            pass
        
        # Guardar la estructura en el diccionario (misma lógica que carpetas_dropbox)
        estructuras_usuarios[usuario.id] = estructura
        
        # Carpetas de este usuario - filtrar según permisos del usuario actual
        if current_user.rol == "cliente":
            # Cliente solo ve carpetas públicas
            folders = Folder.query.filter_by(user_id=usuario.id, es_publica=True).all()
        elif current_user.rol == "lector":
            # Lector ve todas las carpetas del usuario
            folders = Folder.query.filter_by(user_id=usuario.id).all()
        elif current_user.rol == "admin" or current_user.rol == "superadmin":
            # Admin ve todas las carpetas del usuario
            folders = Folder.query.filter_by(user_id=usuario.id).all()
        else:
            # Otros roles solo ven carpetas públicas
            folders = Folder.query.filter_by(user_id=usuario.id, es_publica=True).all()
        
        folders_por_ruta = {f.dropbox_path: f for f in folders}
        
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
    """Oculta un archivo eliminándolo solo de la base de datos, manteniéndolo en Dropbox"""
    from app.models import Archivo, User, Beneficiario
    
    # Verificar que el usuario esté autenticado antes de acceder a sus atributos
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
        return redirect(url_for("auth.login"))
    
    # Verificar permisos del lector
    if current_user.rol == 'lector' and not current_user.puede_eliminar_archivos():
        flash("No tienes permisos para eliminar archivos.", "error")
        redirect_url = request.form.get("redirect_url", "")
        if redirect_url and "/usuario/" in redirect_url:
            return redirect(redirect_url)
        else:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    try:
        # Obtener datos del formulario (el modal usa item_nombre, no archivo_nombre)
        archivo_nombre = request.form.get("item_nombre") or request.form.get("archivo_nombre")
        carpeta_actual = request.form.get("carpeta_actual")
        redirect_url = request.form.get("redirect_url", "")
        
        print(f"DEBUG | Datos recibidos para eliminar archivo:")
        print(f"DEBUG | archivo_nombre: {archivo_nombre}")
        print(f"DEBUG | carpeta_actual: {carpeta_actual}")
        print(f"DEBUG | redirect_url: {redirect_url}")
        print(f"DEBUG | Todos los datos del formulario: {dict(request.form)}")
        
        if not archivo_nombre or not carpeta_actual:
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
        # Obtener el usuario para construir la ruta base
        try:
            usuario_id_int = int(request.form.get("usuario_id"))
            usuario = User.query.get(usuario_id_int)
            if not usuario:
                # Intentar buscar como beneficiario
                usuario = Beneficiario.query.get(usuario_id_int)
            
            if not usuario:
                print(f"DEBUG | Usuario no encontrado con ID: {usuario_id_int}")
                flash("Usuario no encontrado.", "error")
                if redirect_url and "/usuario/" in redirect_url:
                    return redirect(redirect_url)
                else:
                    return redirect(url_for("listar_dropbox.carpetas_dropbox"))
                
        except (ValueError, TypeError):
            print(f"DEBUG | usuario_id inválido: {request.form.get('usuario_id')}")
            flash("ID de usuario inválido.", "error")
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))

        # Construir la ruta base del usuario
        if hasattr(usuario, 'dropbox_folder_path') and usuario.dropbox_folder_path:
            # Si es un User, usar su dropbox_folder_path
            ruta_base = usuario.dropbox_folder_path
        elif hasattr(usuario, 'ruta_base') and usuario.ruta_base:
            # Si es un Beneficiario, usar su ruta_base
            ruta_base = usuario.ruta_base
        else:
            print(f"DEBUG | No se encontró ruta base para usuario: {usuario_id_int}")
            flash("No se encontró la ruta base del usuario.", "error")
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))

        print(f"DEBUG | ruta_base: {ruta_base}")
        
        # Construir la ruta completa del archivo incluyendo la ruta base
        # Asegurar que la ruta base termine con /
        ruta_base_normalizada = ruta_base.rstrip('/') + '/'
        
        if carpeta_actual.startswith(ruta_base_normalizada):
            # Si la carpeta ya incluye la ruta base, usar tal como está
            archivo_path = f"{carpeta_actual}/{archivo_nombre}".replace('//', '/')
        else:
            # Si no incluye la ruta base, agregarla
            archivo_path = f"{ruta_base_normalizada}{carpeta_actual}/{archivo_nombre}".replace('//', '/')
        
        print(f"DEBUG | ruta_base_normalizada: {ruta_base_normalizada}")
        
        print(f"DEBUG | archivo_path construido: {archivo_path}")
        
        # Buscar el archivo en la base de datos
        archivo_bd = Archivo.query.filter_by(dropbox_path=archivo_path).first()
        
        # Si no se encuentra con la ruta exacta, buscar de manera más flexible
        if not archivo_bd:
            print(f"DEBUG | Archivo no encontrado con ruta exacta: {archivo_path}")
            
            # Buscar por nombre y usuario
            archivos_del_usuario = Archivo.query.filter_by(usuario_id=usuario_id_int).all()
            print(f"DEBUG | Archivos del usuario {usuario_id_int}: {len(archivos_del_usuario)}")
            
            for archivo in archivos_del_usuario:
                print(f"DEBUG | Archivo en BD: {archivo.nombre} - {archivo.dropbox_path}")
                if archivo.nombre == archivo_nombre:
                    print(f"DEBUG | Archivo encontrado por nombre: {archivo.nombre}")
                    archivo_bd = archivo
                    break
            
            # Si aún no se encuentra, buscar por nombre en cualquier ruta
            if not archivo_bd:
                archivo_bd = Archivo.query.filter_by(nombre=archivo_nombre).first()
                if archivo_bd:
                    print(f"DEBUG | Archivo encontrado por nombre en cualquier ruta: {archivo_bd.nombre} - {archivo_bd.dropbox_path}")
        
        if not archivo_bd:
            print(f"DEBUG | Archivo no encontrado en BD después de búsqueda flexible: {archivo_nombre}")
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
        # Ocultar el archivo (eliminar solo de la base de datos)
        # El archivo permanece en Dropbox pero se oculta de la interfaz
        db.session.delete(archivo_bd)
        db.session.commit()
        print(f"DEBUG | Archivo ocultado de BD: {archivo_bd.nombre}")
        print(f"DEBUG | Archivo mantenido en Dropbox: {archivo_path}")
        
        # Registrar actividad
        current_user.registrar_actividad('file_hidden', f'Archivo "{archivo_nombre}" ocultado de la interfaz')
        
        
    except Exception as e:
        print(f"ERROR | Error eliminando archivo: {e}")
        flash(f"Error eliminando archivo: {e}", "error")
    
    # Redirigir a la URL apropiada
    if redirect_url and "/usuario/" in redirect_url:
        return redirect(redirect_url)
    else:
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route('/renombrar_carpeta', methods=['POST'])
@login_required
def renombrar_carpeta():
    """Renombra una carpeta en Dropbox y actualiza la base de datos"""
    from app.models import Folder, User, Beneficiario
    
    # Verificar que el usuario esté autenticado
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
        return redirect(url_for("auth.login"))
    
    # Verificar permisos del lector
    if current_user.rol == 'lector' and not current_user.puede_modificar_archivos():
        flash("No tienes permisos para renombrar carpetas.", "error")
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    print("🚩 ¡Llegué a la función renombrar_carpeta!")

    carpeta_nombre_actual = request.form.get("carpeta_nombre_actual")
    carpeta_padre = request.form.get("carpeta_padre")
    usuario_id = request.form.get("usuario_id")
    nuevo_nombre = request.form.get("nuevo_nombre")
    redirect_url = request.form.get("redirect_url", "")

    # Obtener el usuario para construir la ruta base
    try:
        usuario_id_int = int(usuario_id)
        usuario = User.query.get(usuario_id_int)
        if not usuario:
            # Intentar buscar como beneficiario
            usuario = Beneficiario.query.get(usuario_id_int)
        
        if not usuario:
            print(f"DEBUG | Usuario no encontrado con ID: {usuario_id}")
            flash("Usuario no encontrado.", "error")
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
            
    except (ValueError, TypeError):
        print(f"DEBUG | usuario_id inválido: {usuario_id}")
        flash("ID de usuario inválido.", "error")
        if redirect_url and "/usuario/" in redirect_url:
            return redirect(redirect_url)
        else:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    # Construir la ruta base del usuario
    if hasattr(usuario, 'dropbox_folder_path') and usuario.dropbox_folder_path:
        # Si es un User, usar su dropbox_folder_path
        ruta_base = usuario.dropbox_folder_path
    elif hasattr(usuario, 'titular') and usuario.titular and usuario.titular.dropbox_folder_path:
        # Si es un Beneficiario, usar el dropbox_folder_path de su titular
        ruta_base = usuario.titular.dropbox_folder_path
    else:
        # Fallback: usar el email del usuario
        if hasattr(usuario, 'email'):
            ruta_base = f"/{usuario.email}"
        else:
            ruta_base = f"/{usuario.titular.email}" if hasattr(usuario, 'titular') else f"/usuario_{usuario.id}"

    # --- Normalización robusta de path ---
    def join_dropbox_path(parent, name):
        if not parent or parent in ('/', '', None):
            return f"/{name}"
        return f"{parent.rstrip('/')}/{name}"

    # Construir rutas completas incluyendo la ruta base del usuario
    if carpeta_padre.startswith("/"):
        # Si la carpeta padre ya empieza con /, verificar si incluye la ruta base
        if carpeta_padre.startswith(ruta_base):
            # Ya incluye la ruta base, usar directamente
            old_path = join_dropbox_path(carpeta_padre, carpeta_nombre_actual)
            new_path = join_dropbox_path(carpeta_padre, nuevo_nombre)
        else:
            # No incluye la ruta base, agregarla
            carpeta_padre_completa = f"{ruta_base}{carpeta_padre}"
            old_path = join_dropbox_path(carpeta_padre_completa, carpeta_nombre_actual)
            new_path = join_dropbox_path(carpeta_padre_completa, nuevo_nombre)
    else:
        # Si no empieza con /, construir la ruta completa
        carpeta_padre_completa = f"{ruta_base}/{carpeta_padre}"
        old_path = join_dropbox_path(carpeta_padre_completa, carpeta_nombre_actual)
        new_path = join_dropbox_path(carpeta_padre_completa, nuevo_nombre)

    # --- Log antes de buscar carpeta ---
    print("DEBUG | carpeta_nombre_actual:", carpeta_nombre_actual)
    print("DEBUG | carpeta_padre:", carpeta_padre)
    print("DEBUG | usuario_id:", usuario_id)
    print("DEBUG | nuevo_nombre:", nuevo_nombre)
    print("DEBUG | ruta_base:", ruta_base)
    print("DEBUG | old_path:", old_path)
    print("DEBUG | new_path:", new_path)

    if not (carpeta_nombre_actual and usuario_id and nuevo_nombre):
        print("DEBUG | Faltan datos para renombrar carpeta")
        if redirect_url and "/usuario/" in redirect_url:
            return redirect(redirect_url)
        else:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    # Buscar carpeta en la base de datos
    carpeta = Folder.query.filter_by(dropbox_path=old_path).first()
    
    # Si no se encuentra la carpeta exacta, puede ser una carpeta virtual
    if not carpeta and carpeta_padre == "":
        print(f"DEBUG | Carpeta virtual detectada: {carpeta_nombre_actual}")
        print(f"DEBUG | Buscando carpetas que empiecen con /{carpeta_nombre_actual}/")
        
        # Buscar todas las carpetas que empiecen con la ruta de la carpeta virtual
        carpetas_hijas = Folder.query.filter(
            Folder.dropbox_path.startswith(f"/{carpeta_nombre_actual}/")
        ).all()
        
        if not carpetas_hijas:
            print(f"DEBUG | No se encontraron carpetas hijas para: /{carpeta_nombre_actual}/")
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
        print(f"DEBUG | Encontradas {len(carpetas_hijas)} carpetas hijas para renombrar")
        
        # Renombrar todas las carpetas hijas
        dbx = get_dbx()
        try:
            for carpeta_hija in carpetas_hijas:
                old_path_hija = carpeta_hija.dropbox_path
                new_path_hija = old_path_hija.replace(f"/{carpeta_nombre_actual}/", f"/{nuevo_nombre}/", 1)
                
                print(f"DEBUG | Renombrando carpeta hija: {old_path_hija} -> {new_path_hija}")
                
                # Renombrar en Dropbox
                dbx.files_move_v2(with_base_folder(old_path_hija), with_base_folder(new_path_hija), allow_shared_folder=True, autorename=True)
                
                # Actualizar en la base de datos
                carpeta_hija.dropbox_path = new_path_hija
                carpeta_hija.name = carpeta_hija.name  # Mantener el nombre original de la carpeta hija
            
            db.session.commit()
            
            # Registrar actividad
            current_user.registrar_actividad('folder_renamed', f'Carpeta virtual "{carpeta_nombre_actual}" renombrada a "{nuevo_nombre}"')
            
            print(f"DEBUG | Carpeta virtual renombrada exitosamente: {carpeta_nombre_actual} -> {nuevo_nombre}")
            flash("Carpeta renombrada correctamente.", "success")
            
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
                
        except Exception as e:
            print(f"DEBUG | Error renombrando carpeta virtual en Dropbox: {e}")
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    if not carpeta:
        print(f"DEBUG | Carpeta no encontrada en la base para path: {old_path}")
        if redirect_url and "/usuario/" in redirect_url:
            return redirect(redirect_url)
        else:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    dbx = get_dbx()
    try:
        print(f"DEBUG | Renombrando carpeta en Dropbox: {old_path} -> {new_path}")
        dbx.files_move_v2(with_base_folder(old_path), with_base_folder(new_path), allow_shared_folder=True, autorename=True)
    except Exception as e:
        print(f"DEBUG | Error renombrando carpeta en Dropbox: {e}")
        if redirect_url and "/usuario/" in redirect_url:
            return redirect(redirect_url)
        else:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))

    # Actualizar en la base de datos
    carpeta.name = nuevo_nombre
    carpeta.dropbox_path = new_path
    db.session.commit()

    # Registrar actividad
    current_user.registrar_actividad('folder_renamed', f'Carpeta renombrada de "{carpeta_nombre_actual}" a "{nuevo_nombre}"')

    print(f"DEBUG | Carpeta renombrada exitosamente: {old_path} -> {new_path}")
    flash("Carpeta renombrada correctamente.", "success")
    
    # Redirigir a la carpeta específica del usuario
    redirect_url_final = url_for("listar_dropbox.ver_usuario_carpetas", usuario_id=usuario_id_int)
    print(f"🔧 Redirigiendo a usuario específico: /usuario/{usuario_id_int}/carpetas")
    return redirect(redirect_url_final)

@bp.route('/ocultar_carpeta', methods=['POST'])
@login_required
def ocultar_carpeta():
    """Oculta una carpeta eliminándola solo de la base de datos, manteniéndola en Dropbox"""
    from app.models import Folder, User, Beneficiario
    
    # Verificar que el usuario esté autenticado antes de acceder a sus atributos
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
        return redirect(url_for("auth.login"))
    
    # Verificar permisos del lector
    if current_user.rol == 'lector' and not current_user.puede_eliminar_archivos():
        flash("No tienes permisos para ocultar carpetas.", "error")
        redirect_url = request.form.get("redirect_url", "")
        if redirect_url and "/usuario/" in redirect_url:
            return redirect(redirect_url)
        else:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    try:
        # Obtener datos del formulario
        carpeta_nombre = request.form.get("item_nombre") or request.form.get("carpeta_nombre")
        carpeta_actual = request.form.get("carpeta_actual")
        redirect_url = request.form.get("redirect_url", "")
        
        print(f"DEBUG | Datos recibidos para ocultar carpeta:")
        print(f"DEBUG | carpeta_nombre: {carpeta_nombre}")
        print(f"DEBUG | carpeta_actual: {carpeta_actual}")
        print(f"DEBUG | redirect_url: {redirect_url}")
        print(f"DEBUG | Todos los datos del formulario: {dict(request.form)}")
        
        if not carpeta_nombre:
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
        # Obtener el usuario para construir la ruta base
        try:
            usuario_id_int = int(request.form.get("usuario_id"))
            usuario = User.query.get(usuario_id_int)
            if not usuario:
                # Intentar buscar como beneficiario
                usuario = Beneficiario.query.get(usuario_id_int)
            
            if not usuario:
                print(f"DEBUG | Usuario no encontrado con ID: {usuario_id_int}")
                flash("Usuario no encontrado.", "error")
                if redirect_url and "/usuario/" in redirect_url:
                    return redirect(redirect_url)
                else:
                    return redirect(url_for("listar_dropbox.carpetas_dropbox"))
                
        except (ValueError, TypeError):
            print(f"DEBUG | usuario_id inválido: {request.form.get('usuario_id')}")
            flash("ID de usuario inválido.", "error")
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))

        # Construir la ruta base del usuario
        if hasattr(usuario, 'dropbox_folder_path') and usuario.dropbox_folder_path:
            # Si es un User, usar su dropbox_folder_path
            ruta_base = usuario.dropbox_folder_path
        elif hasattr(usuario, 'ruta_base') and usuario.ruta_base:
            # Si es un Beneficiario, usar su ruta_base
            ruta_base = usuario.ruta_base
        else:
            print(f"DEBUG | No se encontró ruta base para usuario: {usuario_id_int}")
            flash("No se encontró la ruta base del usuario.", "error")
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))

        print(f"DEBUG | ruta_base: {ruta_base}")
        
        # Construir la ruta completa de la carpeta
        if carpeta_actual:
            # Si hay carpeta_actual, construir la ruta completa
            carpeta_path = f"{carpeta_actual}/{carpeta_nombre}".replace('//', '/')
        else:
            # Si carpeta_actual está vacío, la carpeta está en la raíz del usuario
            carpeta_path = f"{ruta_base}/{carpeta_nombre}".replace('//', '/')
        
        print(f"DEBUG | carpeta_path construido: {carpeta_path}")
        
        # Buscar la carpeta en la base de datos
        carpeta_bd = Folder.query.filter_by(dropbox_path=carpeta_path).first()
        
        # Si no se encuentra con la ruta exacta, buscar de manera más flexible
        if not carpeta_bd:
            print(f"DEBUG | Carpeta no encontrada con ruta exacta: {carpeta_path}")
            
            # Buscar por nombre y usuario
            carpetas_del_usuario = Folder.query.filter_by(user_id=usuario_id_int).all()
            print(f"DEBUG | Carpetas del usuario {usuario_id_int}: {len(carpetas_del_usuario)}")
            
            for carpeta in carpetas_del_usuario:
                print(f"DEBUG | Carpeta en BD: {carpeta.name} - {carpeta.dropbox_path}")
                if carpeta.name == carpeta_nombre:
                    print(f"DEBUG | Carpeta encontrada por nombre: {carpeta.name}")
                    carpeta_bd = carpeta
                    break
            
            # Si aún no se encuentra, buscar por nombre en cualquier ruta
            if not carpeta_bd:
                carpeta_bd = Folder.query.filter_by(name=carpeta_nombre).first()
                if carpeta_bd:
                    print(f"DEBUG | Carpeta encontrada por nombre en cualquier ruta: {carpeta_bd.name} - {carpeta_bd.dropbox_path}")
        
        if not carpeta_bd:
            print(f"DEBUG | Carpeta no encontrada en BD después de búsqueda flexible: {carpeta_nombre}")
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
        # Ocultar la carpeta (eliminar solo de la base de datos)
        # La carpeta permanece en Dropbox pero se oculta de la interfaz
        db.session.delete(carpeta_bd)
        db.session.commit()
        print(f"DEBUG | Carpeta ocultada de BD: {carpeta_bd.name}")
        print(f"DEBUG | Carpeta mantenida en Dropbox: {carpeta_path}")
        
        # Registrar actividad
        current_user.registrar_actividad('folder_hidden', f'Carpeta "{carpeta_nombre}" ocultada de la interfaz')
        
    except Exception as e:
        print(f"ERROR | Error ocultando carpeta: {e}")
        flash(f"Error ocultando carpeta: {e}", "error")
    
    # Redirigir a la URL apropiada
    if redirect_url and "/usuario/" in redirect_url:
        return redirect(redirect_url)
    else:
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route('/eliminar_carpeta', methods=['POST'])
@login_required
def eliminar_carpeta():
    """Elimina una carpeta de Dropbox y de la base de datos"""
    from app.models import Folder, Archivo
    
    # Verificar que el usuario esté autenticado
    if not current_user.is_authenticated or not hasattr(current_user, "rol"):
        flash("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", "error")
        return redirect(url_for("auth.login"))
    
    # Verificar permisos del lector
    if current_user.rol == 'lector' and not current_user.puede_eliminar_archivos():
        flash("No tienes permisos para eliminar carpetas.", "error")
        redirect_url = request.form.get("redirect_url", "")
        if redirect_url and "/usuario/" in redirect_url:
            return redirect(redirect_url)
        else:
            return redirect(url_for("listar_dropbox.carpetas_dropbox"))
    
    try:
        carpeta_nombre = request.form.get("carpeta_nombre")
        carpeta_padre = request.form.get("carpeta_padre")
        redirect_url = request.form.get("redirect_url", "")
        
        if not carpeta_nombre or not carpeta_padre:
            if redirect_url and "/usuario/" in redirect_url:
                return redirect(redirect_url)
            else:
                return redirect(url_for("listar_dropbox.carpetas_dropbox"))
        
        # Construir la ruta completa de la carpeta
        carpeta_path = f"{carpeta_padre}/{carpeta_nombre}".replace('//', '/')
        
        print(f"DEBUG | Eliminando carpeta: {carpeta_path}")
        
        # Conectar a Dropbox
        dbx = get_dbx()
        
        # Eliminar carpeta de Dropbox (esto eliminará recursivamente todo el contenido)
        try:
            dbx.files_delete_v2(carpeta_path)
            print(f"DEBUG | Carpeta eliminada de Dropbox: {carpeta_path}")
        except dropbox.exceptions.ApiError as e:
            if "not_found" in str(e):
                print(f"DEBUG | Carpeta no encontrada en Dropbox: {carpeta_path}")
            else:
                raise e
        
        # Eliminar registros de la base de datos
        # Primero eliminar archivos que estén en esta carpeta
        archivos_eliminados = Archivo.query.filter(Archivo.dropbox_path.like(f"{carpeta_path}/%")).delete()
        print(f"DEBUG | Archivos eliminados de BD: {archivos_eliminados}")
        
        # Luego eliminar la carpeta
        carpeta_bd = Folder.query.filter_by(dropbox_path=carpeta_path).first()
        if carpeta_bd:
            db.session.delete(carpeta_bd)
            print(f"DEBUG | Carpeta eliminada de BD: {carpeta_bd.name}")
        
        db.session.commit()
        
        # Registrar actividad
        current_user.registrar_actividad('folder_deleted', f'Carpeta "{carpeta_nombre}" eliminada')
        
        flash("Carpeta eliminada correctamente.", "success")
        
    except Exception as e:
        print(f"ERROR | Error eliminando carpeta: {e}")
        flash(f"Error eliminando carpeta: {e}", "error")
    
    # Redirigir a la URL apropiada
    if redirect_url and "/usuario/" in redirect_url:
        return redirect(redirect_url)
    else:
        return redirect(url_for("listar_dropbox.carpetas_dropbox"))

@bp.route("/buscar_archivos_avanzada", methods=["GET", "POST"])
@login_required
def buscar_archivos_avanzada():
    """Búsqueda avanzada de archivos con múltiples filtros"""
    from app.models import Archivo, User, Beneficiario
    
    if request.method == "GET":
        # Obtener datos para los filtros
        usuarios = User.query.filter_by(es_beneficiario=False).all()
        beneficiarios = Beneficiario.query.all()
        categorias = list(CATEGORIAS.keys())
        
        return render_template(
            "busqueda_avanzada.html",
            usuarios=usuarios,
            beneficiarios=beneficiarios,
            categorias=categorias,
            categorias_json=json.dumps(CATEGORIAS)
        )
    
    # POST: procesar búsqueda
    try:
        # Obtener parámetros de búsqueda
        query = request.form.get("query", "").strip()
        usuario_id = request.form.get("usuario_id", "")
        categoria = request.form.get("categoria", "")
        subcategoria = request.form.get("subcategoria", "")
        fecha_desde = request.form.get("fecha_desde", "")
        fecha_hasta = request.form.get("fecha_hasta", "")
        extension = request.form.get("extension", "")
        tamano_min = request.form.get("tamano_min", "")
        tamano_max = request.form.get("tamano_max", "")
        
        # Construir consulta base
        consulta = Archivo.query
        
        # Filtros
        if query:
            consulta = consulta.filter(
                db.or_(
                    Archivo.nombre.ilike(f"%{query}%"),
                    Archivo.descripcion.ilike(f"%{query}%"),
                    Archivo.categoria.ilike(f"%{query}%"),
                    Archivo.subcategoria.ilike(f"%{query}%")
                )
            )
        
        if usuario_id:
            if usuario_id.startswith("user-"):
                real_id = int(usuario_id[5:])
                consulta = consulta.filter(Archivo.usuario_id == real_id)
            elif usuario_id.startswith("beneficiario-"):
                # Para beneficiarios, buscar por el titular
                real_id = int(usuario_id[13:])
                beneficiario = Beneficiario.query.get(real_id)
                if beneficiario and beneficiario.titular_id:
                    consulta = consulta.filter(Archivo.usuario_id == beneficiario.titular_id)
        
        if categoria:
            consulta = consulta.filter(Archivo.categoria == categoria)
        
        if subcategoria:
            consulta = consulta.filter(Archivo.subcategoria == subcategoria)
        
        if fecha_desde:
            try:
                fecha_desde_obj = datetime.strptime(fecha_desde, "%Y-%m-%d")
                consulta = consulta.filter(Archivo.fecha_subida >= fecha_desde_obj)
            except ValueError:
                pass
        
        if fecha_hasta:
            try:
                fecha_hasta_obj = datetime.strptime(fecha_hasta, "%Y-%m-%d")
                consulta = consulta.filter(Archivo.fecha_subida <= fecha_hasta_obj)
            except ValueError:
                pass
        
        if extension:
            consulta = consulta.filter(Archivo.nombre.ilike(f"%.{extension}"))
        
        if tamano_min:
            try:
                tamano_min_bytes = int(tamano_min) * 1024 * 1024  # Convertir MB a bytes
                consulta = consulta.filter(Archivo.tamano >= tamano_min_bytes)
            except ValueError:
                pass
        
        if tamano_max:
            try:
                tamano_max_bytes = int(tamano_max) * 1024 * 1024  # Convertir MB a bytes
                consulta = consulta.filter(Archivo.tamano <= tamano_max_bytes)
            except ValueError:
                pass
        
        # Ejecutar consulta
        archivos = consulta.order_by(Archivo.fecha_subida.desc()).all()
        
        # Preparar resultados
        resultados = []
        for archivo in archivos:
            usuario = User.query.get(archivo.usuario_id) if archivo.usuario_id else None
            resultados.append({
                'id': archivo.id,
                'nombre': archivo.nombre,
                'categoria': archivo.categoria,
                'subcategoria': archivo.subcategoria,
                'dropbox_path': archivo.dropbox_path,
                'fecha_subida': archivo.fecha_subida.strftime("%d/%m/%Y %H:%M") if archivo.fecha_subida else "",
                'tamano': archivo.tamano,
                'extension': archivo.extension,
                'descripcion': archivo.descripcion,
                'usuario': usuario.nombre_completo if usuario else "Sin usuario",
                'usuario_email': usuario.email if usuario else ""
            })
        
        # Registrar actividad
        current_user.registrar_actividad('advanced_search', f'Búsqueda avanzada realizada con {len(resultados)} resultados')
        
        return jsonify({
            'success': True,
            'resultados': resultados,
            'total': len(resultados)
        })
        
    except Exception as e:
        print(f"Error en búsqueda avanzada: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route("/notificaciones", methods=["GET"])
@login_required
def obtener_notificaciones():
    """Obtiene las notificaciones del usuario actual"""
    from app.models import Notification
    
    # Obtener notificaciones no leídas
    notificaciones = Notification.query.filter_by(
        user_id=current_user.id,
        leida=False
    ).order_by(Notification.fecha_creacion.desc()).limit(10).all()
    
    # Preparar datos para JSON
    datos = []
    for notif in notificaciones:
        datos.append({
            'id': notif.id,
            'titulo': notif.titulo,
            'mensaje': notif.mensaje,
            'tipo': notif.tipo,
            'fecha': notif.fecha_creacion.strftime("%d/%m/%Y %H:%M"),
            'leida': notif.leida
        })
    
    return jsonify({
        'success': True,
        'notificaciones': datos,
        'total': len(datos)
    })

@bp.route("/notificaciones/marcar_leida/<int:notif_id>", methods=["POST"])
@login_required
def marcar_notificacion_leida(notif_id):
    """Marca una notificación como leída"""
    from app.models import Notification
    
    notificacion = Notification.query.filter_by(
        id=notif_id,
        user_id=current_user.id
    ).first()
    
    if notificacion:
        notificacion.marcar_como_leida()
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Notificación no encontrada'}), 404

@bp.route("/notificaciones/marcar_todas_leidas", methods=["POST"])
@login_required
def marcar_todas_notificaciones_leidas():
    """Marca todas las notificaciones del usuario como leídas"""
    from app.models import Notification
    
    notificaciones = Notification.query.filter_by(
        user_id=current_user.id,
        leida=False
    ).all()
    
    for notif in notificaciones:
        notif.marcar_como_leida()
    
    db.session.commit()
    
    return jsonify({'success': True})

def crear_notificacion(usuario_id, titulo, mensaje, tipo='info'):
    """Función helper para crear notificaciones"""
    from app.models import Notification
    
    notificacion = Notification(
        user_id=usuario_id,
        titulo=titulo,
        mensaje=mensaje,
        tipo=tipo
    )
    db.session.add(notificacion)
    db.session.commit()
    
    return notificacion


