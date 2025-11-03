"""
Utilidades para el sistema de notificaciones
"""
from app.models import User, Notification, Beneficiario
from app import db
from datetime import datetime
from typing import Optional
from flask import current_app
import traceback


def notificar_archivo_subido(nombre_archivo: str, usuario_subio, categoria: str, archivo_id: Optional[int] = None):
    """
    Envía notificaciones a usuarios admin y lector cuando se sube un archivo
    
    Args:
        nombre_archivo: Nombre del archivo subido
        usuario_subio: Usuario o Beneficiario que subió el archivo
        categoria: Categoría del archivo subido
        archivo_id: ID del archivo subido (opcional)
    """
    try:
        # Determinar nombre del usuario que subió
        if isinstance(usuario_subio, Beneficiario):
            nombre_usuario = f"{usuario_subio.nombre} {usuario_subio.lastname or ''}".strip()
            tipo_usuario = "beneficiario"
            rol_usuario = None
        else:
            nombre_usuario = usuario_subio.nombre_completo
            rol_usuario = getattr(usuario_subio, 'rol', None)
            tipo_usuario = rol_usuario or "usuario"
        
        # Preparar mensaje según quién subió
        titulo = "Nuevo archivo subido"
        if rol_usuario in ['admin', 'superadmin', 'lector']:
            # Mensaje para cuando un admin/lector sube archivo
            mensaje = f"Has subido un nuevo archivo: {nombre_archivo}"
        else:
            # Mensaje para cuando un cliente/beneficiario sube archivo
            mensaje = f"{nombre_usuario} ({tipo_usuario}) ha subido un nuevo archivo: {nombre_archivo}"
        
        if categoria:
            mensaje += f" en la categoría {categoria}"
        
        # Obtener todos los usuarios admin y lector
        usuarios_notificar = User.query.filter(
            User.rol.in_(['admin', 'superadmin', 'lector'])
        ).all()
        
        try:
            current_app.logger.info(f"🔔 Preparando notificaciones - Archivo: {nombre_archivo}, Archivo ID: {archivo_id}, Usuario subió: {nombre_usuario}, Rol: {getattr(usuario_subio, 'rol', 'N/A')}, Usuarios a notificar: {len(usuarios_notificar)}")
        except Exception:
            print(f"🔔 DEBUG: Preparando notificaciones - Archivo: {nombre_archivo}, Archivo ID: {archivo_id}, Usuario subió: {nombre_usuario}, Rol: {getattr(usuario_subio, 'rol', 'N/A')}, Usuarios a notificar: {len(usuarios_notificar)}")
        
        # Verificar que hay usuarios para notificar
        if not usuarios_notificar:
            print("⚠️ WARNING: No hay usuarios admin/lector para notificar")
            return False
        
        # Crear notificaciones para cada usuario
        notificaciones_enviadas = 0
        notificaciones_creadas = []
        
        for usuario in usuarios_notificar:
            # Notificar a todos los admin/lector, incluyendo quien subió el archivo
            # Solo omitir si quien subió es un cliente
            if isinstance(usuario_subio, User) and usuario.id == usuario_subio.id and usuario_subio.rol == 'cliente':
                try:
                    current_app.logger.info(f"⏭️ Omitiendo notificación para cliente que subió archivo (ID: {usuario.id})")
                except Exception:
                    print(f"⏭️ Omitiendo notificación para cliente que subió archivo (ID: {usuario.id})")
                continue
            
            try:
                # Personalizar el mensaje según quién recibe la notificación
                mensaje_personalizado = mensaje
                titulo_personalizado = titulo
                
                # Si quien recibe es quien subió el archivo
                if isinstance(usuario_subio, User) and usuario.id == usuario_subio.id:
                    titulo_personalizado = "Archivo subido exitosamente"
                    mensaje_personalizado = f"Has subido exitosamente el archivo: {nombre_archivo}"
                    if categoria:
                        mensaje_personalizado += f" en la categoría {categoria}"
                
                notificacion = Notification(
                    user_id=usuario.id,
                    archivo_id=archivo_id,
                    titulo=titulo_personalizado,
                    mensaje=mensaje_personalizado,
                    tipo='info',
                    leida=False,
                    fecha_creacion=datetime.utcnow()
                )
                db.session.add(notificacion)
                notificaciones_creadas.append(notificacion)
                notificaciones_enviadas += 1
                try:
                    current_app.logger.info(f"🔔 Notificación creada para usuario ID {usuario.id} ({usuario.email}) - Archivo ID: {archivo_id}")
                except Exception:
                    print(f"🔔 DEBUG: Notificación creada para usuario ID {usuario.id} ({usuario.email}) - Archivo ID: {archivo_id}")
            except Exception as e_notif:
                print(f"❌ ERROR al crear notificación para usuario {usuario.id}: {e_notif}")
                traceback.print_exc()
                continue
        
        # Confirmar las notificaciones solo si se crearon algunas
        if notificaciones_creadas:
            try:
                db.session.commit()
                try:
                    current_app.logger.info(f"✅ {notificaciones_enviadas} notificaciones guardadas exitosamente en la base de datos")
                except Exception:
                    print(f"✅ {notificaciones_enviadas} notificaciones guardadas exitosamente en la base de datos")
                
                # Verificar que se guardaron correctamente consultando la BD
                for notif in notificaciones_creadas:
                    try:
                        # Consultar directamente en la BD para verificar
                        notif_id = notif.id if hasattr(notif, 'id') and notif.id else None
                        if notif_id:
                            notif_verificada = Notification.query.get(notif_id)
                            if notif_verificada:
                                try:
                                    current_app.logger.info(f"✅ Verificado: Notificación ID {notif_id} guardada correctamente en BD (Usuario: {notif_verificada.user_id}, Archivo: {notif_verificada.archivo_id})")
                                except Exception:
                                    print(f"✅ Verificado: Notificación ID {notif_id} guardada correctamente en BD (Usuario: {notif_verificada.user_id}, Archivo: {notif_verificada.archivo_id})")
                            else:
                                print(f"❌ ERROR: Notificación ID {notif_id} no encontrada en la base de datos después del commit")
                        else:
                            print(f"⚠️ WARNING: Notificación no tiene ID asignado después del commit")
                    except Exception as e_verif:
                        print(f"⚠️ WARNING: No se pudo verificar notificación: {e_verif}")
                        traceback.print_exc()
                
                return True
            except Exception as e_commit:
                db.session.rollback()
                print(f"❌ ERROR al hacer commit de notificaciones: {e_commit}")
                traceback.print_exc()
                return False
        else:
            print("⚠️ WARNING: No se crearon notificaciones para guardar")
            return False
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ ERROR general al enviar notificaciones: {e}")
        import traceback
        traceback.print_exc()
        return False


def obtener_notificaciones_no_leidas(user_id: int):
    """
    Obtiene las notificaciones no leídas de un usuario
    
    Args:
        user_id: ID del usuario
        
    Returns:
        Lista de notificaciones no leídas
    """
    try:
        notificaciones = Notification.query.filter_by(
            user_id=user_id,
            leida=False
        ).order_by(Notification.fecha_creacion.desc()).all()
        return notificaciones
    except Exception as e:
        print(f"Error al obtener notificaciones: {e}")
        return []


def contar_notificaciones_no_leidas(user_id: int):
    """
    Cuenta las notificaciones no leídas de un usuario
    
    Args:
        user_id: ID del usuario
        
    Returns:
        Número de notificaciones no leídas
    """
    try:
        count = Notification.query.filter_by(
            user_id=user_id,
            leida=False
        ).count()
        return count
    except Exception as e:
        print(f"Error al contar notificaciones: {e}")
        return 0


def marcar_notificacion_leida(notificacion_id: int, user_id: int):
    """
    Marca una notificación como leída
    
    Args:
        notificacion_id: ID de la notificación
        user_id: ID del usuario (para validación)
        
    Returns:
        True si se marcó correctamente, False en caso contrario
    """
    try:
        notificacion = Notification.query.filter_by(
            id=notificacion_id,
            user_id=user_id
        ).first()
        
        if notificacion:
            notificacion.leida = True
            notificacion.fecha_leida = datetime.utcnow()
            db.session.commit()
            return True
        
        return False
        
    except Exception as e:
        db.session.rollback()
        print(f"Error al marcar notificación como leída: {e}")
        return False


def marcar_todas_notificaciones_leidas(user_id: int):
    """
    Marca todas las notificaciones de un usuario como leídas
    
    Args:
        user_id: ID del usuario
        
    Returns:
        True si se marcaron correctamente, False en caso contrario
    """
    try:
        notificaciones = Notification.query.filter_by(
            user_id=user_id,
            leida=False
        ).all()
        
        for notif in notificaciones:
            notif.leida = True
            notif.fecha_leida = datetime.utcnow()
        
        db.session.commit()
        return True
        
    except Exception as e:
        db.session.rollback()
        print(f"Error al marcar todas las notificaciones como leídas: {e}")
        return False

