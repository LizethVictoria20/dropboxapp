"""
Módulo para enviar notificaciones externas (Email, SMS, WhatsApp)
cuando se rechaza un documento o cambia su estado.
"""
import os
from typing import Optional, Dict, List
from flask import current_app
from app.models import User, Archivo
import traceback
from typing import Any
import socket
import threading
from contextlib import contextmanager

# Intentar importar dependencias opcionales
try:
    from flask_mail import Mail, Message
    FLASK_MAIL_AVAILABLE = True
except ImportError:
    FLASK_MAIL_AVAILABLE = False
    Mail = None  # type: ignore[assignment]
    Message = None  # type: ignore[assignment]

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    TwilioClient = None  # type: ignore[assignment]


_socket_patch_lock = threading.Lock()


@contextmanager
def _force_ipv4_only():
    """Temporarily force DNS resolution to IPv4 only.

    This helps on servers without IPv6 egress where a hostname (e.g. smtp.gmail.com)
    resolves to IPv6 first and connection fails with Errno 101.

    Note: This patches socket.getaddrinfo process-wide, so we guard with a lock.
    """
    original_getaddrinfo = socket.getaddrinfo

    def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):  # type: ignore[no-untyped-def]
        return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    with _socket_patch_lock:
        socket.getaddrinfo = ipv4_getaddrinfo  # type: ignore[assignment]
        try:
            yield
        finally:
            socket.getaddrinfo = original_getaddrinfo  # type: ignore[assignment]


def _should_force_ipv4() -> bool:
    return _env_bool('MAIL_FORCE_IPV4', False)


def _send_mail_with_optional_ipv4(mail: Any, msg: Any, description: str) -> None:
    """Send email, optionally forcing IPv4 based on env var.

    If MAIL_FORCE_IPV4=true, always send under IPv4-only resolver.
    Otherwise, do a best-effort retry on Errno 101 (Network is unreachable).
    """
    if _should_force_ipv4():
        current_app.logger.warning("MAIL_FORCE_IPV4=true: enviando %s forzando IPv4", description)
        with _force_ipv4_only():
            mail.send(msg)
        return

    try:
        mail.send(msg)
    except OSError as e:
        if getattr(e, 'errno', None) == 101:
            current_app.logger.warning(
                "Fallo enviando %s por IPv6 sin salida (Errno 101). Reintentando forzando IPv4.",
                description,
            )
            with _force_ipv4_only():
                current_app.logger.info("Intento IPv4 iniciado para %s", description)
                mail.send(msg)
                current_app.logger.info("Intento IPv4 finalizado para %s", description)
            return
        raise


def _env_bool(name: str, default: bool) -> bool:
    """Parse common boolean env values."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    raw = str(raw).strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _mail_config_summary(
    mail_server: Optional[str],
    mail_port: int,
    mail_use_tls: bool,
    mail_use_ssl: bool,
    mail_username: Optional[str],
    mail_sender: Optional[str],
    suppress_send: bool,
) -> str:
    server_display = mail_server or ""
    if len(server_display) > 80:
        server_display = server_display[:77] + "..."
    username_hint = (mail_username or "")
    if username_hint and "@" in username_hint:
        user_display = username_hint.split("@", 1)[0] + "@…"
    else:
        user_display = bool(username_hint)
    return (
        f"MAIL_SERVER={server_display or bool(mail_server)} PORT={mail_port} TLS={mail_use_tls} SSL={mail_use_ssl} "
        f"USERNAME={user_display} DEFAULT_SENDER={bool(mail_sender)} SUPPRESS_SEND={suppress_send}"
    )


def enviar_notificacion_documento_validado(
    usuario: User,
    archivo: Archivo,
    comentario: Optional[str] = None
) -> Dict[str, bool]:
    """
    Envía notificaciones externas (email) cuando un documento es validado/aprobado.
    
    Args:
        usuario: Usuario propietario del archivo
        archivo: Archivo que fue validado
        comentario: Comentario opcional
    
    Returns:
        Dict con el estado de cada tipo de notificación enviada
    """
    resultados = {
        'email': False,
        'sms': False,
        'whatsapp': False
    }
    
    try:
        nombre_usuario = usuario.nombre_completo or usuario.email.split('@')[0]
        app_url = os.environ.get('APP_URL') or 'http://localhost:5000'
        url_archivo = f"{app_url}/carpetas_dropbox"
        
        # Enviar email de aprobación
        if usuario.email:
            resultados['email'] = enviar_email_validado(
                destinatario=usuario.email,
                nombre_usuario=nombre_usuario,
                nombre_archivo=archivo.nombre,
                comentario=comentario,
                url_archivo=url_archivo
            )
        
        if resultados['email']:
            current_app.logger.info(
                f"✅ Email de validación enviado para archivo '{archivo.nombre}' a {usuario.email}"
            )
        
    except Exception as e:
        current_app.logger.error(f"❌ Error al enviar notificación de validación: {e}")
        traceback.print_exc()
    
    return resultados


def enviar_notificacion_documento_rechazado(
    usuario: User,
    archivo: Archivo,
    comentario: Optional[str] = None
) -> Dict[str, bool]:
    """
    Envía notificaciones externas (email, SMS, WhatsApp) cuando un documento es rechazado.
    
    Args:
        usuario: Usuario propietario del archivo
        archivo: Archivo que fue rechazado
        comentario: Comentario opcional sobre el rechazo
    
    Returns:
        Dict con el estado de cada tipo de notificación enviada
    """
    resultados = {
        'email': False,
        'sms': False,
        'whatsapp': False
    }
    
    try:
        # Preparar mensaje
        nombre_usuario = usuario.nombre_completo or usuario.email.split('@')[0]
        mensaje_base = f"Tu documento '{archivo.nombre}' ha sido rechazado."
        if comentario:
            mensaje_base += f" Motivo: {comentario}"
        mensaje_base += " Por favor, ingresa a la aplicación para revisar los detalles y subir una nueva versión."
        
        # URL de la aplicación (ajustar según tu dominio)
        app_url = os.environ.get('APP_URL') or 'http://localhost:5000'
        # Usar la ruta directamente en lugar de url_for para evitar problemas de contexto
        url_archivo = f"{app_url}/carpetas_dropbox"
        
        # Enviar email
        if usuario.email:
            resultados['email'] = enviar_email_rechazo(
                destinatario=usuario.email,
                nombre_usuario=nombre_usuario,
                nombre_archivo=archivo.nombre,
                comentario=comentario,
                url_archivo=url_archivo
            )
        
        # Enviar SMS
        if usuario.telefono:
            resultados['sms'] = enviar_sms_rechazo(
                telefono=usuario.telefono,
                nombre_usuario=nombre_usuario,
                nombre_archivo=archivo.nombre,
                url_archivo=url_archivo
            )
        
        # Enviar WhatsApp
        if usuario.telefono:
            resultados['whatsapp'] = enviar_whatsapp_rechazo(
                telefono=usuario.telefono,
                nombre_usuario=nombre_usuario,
                nombre_archivo=archivo.nombre,
                comentario=comentario,
                url_archivo=url_archivo
            )
        
        # Log de resultados
        notificaciones_exitosas = sum(1 for v in resultados.values() if v)
        if notificaciones_exitosas > 0:
            current_app.logger.info(
                f"✅ Notificaciones externas enviadas para archivo rechazado '{archivo.nombre}': "
                f"Email: {resultados['email']}, SMS: {resultados['sms']}, WhatsApp: {resultados['whatsapp']}"
            )
        else:
            current_app.logger.warning(
                f"⚠️ No se pudieron enviar notificaciones externas para archivo rechazado '{archivo.nombre}'"
            )
        
    except Exception as e:
        current_app.logger.error(f"❌ Error al enviar notificaciones externas: {e}")
        traceback.print_exc()
    
    return resultados


def enviar_email_validado(
    destinatario: str,
    nombre_usuario: str,
    nombre_archivo: str,
    comentario: Optional[str] = None,
    url_archivo: Optional[str] = None
) -> bool:
    """
    Envía un email notificando la aprobación/validación de un documento.
    
    Returns:
        True si se envió exitosamente, False en caso contrario
    """
    if (not FLASK_MAIL_AVAILABLE) or Mail is None or Message is None:
        current_app.logger.warning("Flask-Mail no está disponible. Instala con: pip install flask-mail")
        return False
    
    try:
        mail_server = os.environ.get('MAIL_SERVER') or current_app.config.get('MAIL_SERVER')
        mail_port = int(os.environ.get('MAIL_PORT') or current_app.config.get('MAIL_PORT', 587))
        mail_use_tls = _env_bool('MAIL_USE_TLS', bool(current_app.config.get('MAIL_USE_TLS', True)))
        mail_use_ssl = _env_bool('MAIL_USE_SSL', bool(current_app.config.get('MAIL_USE_SSL', False)))
        mail_timeout = int(os.environ.get('MAIL_TIMEOUT') or current_app.config.get('MAIL_TIMEOUT', 10))
        mail_username = os.environ.get('MAIL_USERNAME') or current_app.config.get('MAIL_USERNAME')
        mail_password = (os.environ.get('MAIL_PASSWORD') or current_app.config.get('MAIL_PASSWORD') or '')
        mail_password = str(mail_password).replace(' ', '')
        mail_sender = (os.environ.get('MAIL_DEFAULT_SENDER') or 
                      current_app.config.get('MAIL_DEFAULT_SENDER') or 
                      mail_username)

        suppress_send = _env_bool('MAIL_SUPPRESS_SEND', bool(current_app.config.get('MAIL_SUPPRESS_SEND', False)))
        
        if not all([mail_server, mail_username, mail_password]):
            missing = []
            if not mail_server:
                missing.append('MAIL_SERVER')
            if not mail_username:
                missing.append('MAIL_USERNAME')
            if not mail_password:
                missing.append('MAIL_PASSWORD')
            current_app.logger.warning(
                "Configuración de email incompleta. Faltan: %s. (%s)"
                % (', '.join(missing), _mail_config_summary(mail_server, mail_port, mail_use_tls, mail_use_ssl, mail_username, mail_sender, suppress_send))
            )
            return False

        # Aplicar config (útil si Flask-Mail se inicializó antes de que existieran env vars)
        current_app.config.update({
            'MAIL_SERVER': mail_server,
            'MAIL_PORT': mail_port,
            'MAIL_USE_TLS': mail_use_tls,
            'MAIL_USE_SSL': mail_use_ssl,
            'MAIL_TIMEOUT': mail_timeout,
            'MAIL_USERNAME': mail_username,
            'MAIL_PASSWORD': mail_password,
            'MAIL_DEFAULT_SENDER': mail_sender,
            'MAIL_SUPPRESS_SEND': suppress_send,
        })
        
        if not hasattr(current_app, 'extensions') or 'mail' not in current_app.extensions:
            current_app.logger.warning(
                "Flask-Mail no estaba inicializado en app.extensions; inicializando on-demand. (%s)"
                % _mail_config_summary(mail_server, mail_port, mail_use_tls, mail_use_ssl, mail_username, mail_sender, suppress_send)
            )
            mail = Mail(current_app)
        else:
            mail = current_app.extensions['mail']

        # Asegurar que el objeto Mail use la configuración actual (Mail no re-lee app.config dinámicamente)
        try:
            mail.server = mail_server
            mail.port = mail_port
            mail.use_tls = mail_use_tls
            mail.use_ssl = mail_use_ssl
            mail.username = mail_username
            mail.password = mail_password
            mail.default_sender = mail_sender
            mail.suppress_send = suppress_send
            mail.timeout = mail_timeout
        except Exception:
            # Si por alguna razón no tiene esos atributos, continuamos con la instancia tal cual
            pass
        
        asunto = f"✅ Documento Aprobado: {nombre_archivo}"
        
        cuerpo_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #4caf50;">✅ Documento Aprobado</h2>
                <p>Hola {nombre_usuario},</p>
                <p>¡Buenas noticias! Tu documento <strong>{nombre_archivo}</strong> ha sido <strong style="color: #4caf50;">aprobado</strong>.</p>
        """
        
        if comentario:
            cuerpo_html += f"""
                <div style="background-color: #e8f5e9; border-left: 4px solid #4caf50; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>Comentario:</strong></p>
                    <p style="margin: 5px 0 0 0;">{comentario}</p>
                </div>
            """
        
        cuerpo_html += """
                <p>Tu documentación está en orden. Gracias por tu colaboración.</p>
        """
        
        if url_archivo:
            cuerpo_html += f"""
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{url_archivo}" 
                       style="background-color: #4caf50; color: white; padding: 12px 24px; 
                              text-decoration: none; border-radius: 4px; display: inline-block;">
                        Ver Documentos
                    </a>
                </div>
            """
        
        cuerpo_html += """
                <p style="margin-top: 30px; font-size: 12px; color: #666;">
                    Este es un mensaje automático. Por favor, no respondas a este correo.
                </p>
            </div>
        </body>
        </html>
        """
        
        cuerpo_texto = f"""
Hola {nombre_usuario},

¡Buenas noticias! Tu documento "{nombre_archivo}" ha sido APROBADO.
        """
        
        if comentario:
            cuerpo_texto += f"\nComentario: {comentario}\n"
        
        cuerpo_texto += "\nTu documentación está en orden. Gracias por tu colaboración.\n"
        
        if url_archivo:
            cuerpo_texto += f"\nAccede aquí: {url_archivo}\n"
        
        msg = Message(
            subject=asunto,
            recipients=[destinatario],
            sender=mail_sender,
            html=cuerpo_html,
            body=cuerpo_texto
        )

        current_app.logger.info(
            "Enviando email de aprobación a %s (%s) timeout=%ss force_ipv4=%s" % (
                destinatario,
                _mail_config_summary(mail_server, mail_port, mail_use_tls, mail_use_ssl, mail_username, mail_sender, suppress_send),
                mail_timeout,
                _should_force_ipv4(),
            )
        )
        
        _send_mail_with_optional_ipv4(mail, msg, "email de aprobación")
        current_app.logger.info(f"✅ Email de aprobación enviado exitosamente a {destinatario}")
        return True
        
    except Exception as e:
        current_app.logger.exception(f"❌ Error al enviar email de aprobación: {e}")
        return False


def enviar_email_rechazo(
    destinatario: str,
    nombre_usuario: str,
    nombre_archivo: str,
    comentario: Optional[str] = None,
    url_archivo: Optional[str] = None
) -> bool:
    """
    Envía un email notificando el rechazo de un documento.
    Soporta Gmail gratuito y otros servidores SMTP.
    
    Returns:
        True si se envió exitosamente, False en caso contrario
    """
    if (not FLASK_MAIL_AVAILABLE) or Mail is None or Message is None:
        current_app.logger.warning("Flask-Mail no está disponible. Instala con: pip install flask-mail")
        return False
    
    try:
        # Obtener configuración de email desde variables de entorno o config
        mail_server = os.environ.get('MAIL_SERVER') or current_app.config.get('MAIL_SERVER')
        mail_port = int(os.environ.get('MAIL_PORT') or current_app.config.get('MAIL_PORT', 587))
        mail_use_tls = _env_bool('MAIL_USE_TLS', bool(current_app.config.get('MAIL_USE_TLS', True)))
        mail_use_ssl = _env_bool('MAIL_USE_SSL', bool(current_app.config.get('MAIL_USE_SSL', False)))
        mail_timeout = int(os.environ.get('MAIL_TIMEOUT') or current_app.config.get('MAIL_TIMEOUT', 10))
        mail_username = os.environ.get('MAIL_USERNAME') or current_app.config.get('MAIL_USERNAME')
        mail_password = (os.environ.get('MAIL_PASSWORD') or current_app.config.get('MAIL_PASSWORD') or '')
        mail_password = str(mail_password).replace(' ', '')
        mail_sender = (os.environ.get('MAIL_DEFAULT_SENDER') or 
                      current_app.config.get('MAIL_DEFAULT_SENDER') or 
                      mail_username)

        suppress_send = _env_bool('MAIL_SUPPRESS_SEND', bool(current_app.config.get('MAIL_SUPPRESS_SEND', False)))
        
        # Verificar configuración mínima
        if not all([mail_server, mail_username, mail_password]):
            missing = []
            if not mail_server:
                missing.append('MAIL_SERVER')
            if not mail_username:
                missing.append('MAIL_USERNAME')
            if not mail_password:
                missing.append('MAIL_PASSWORD')
            current_app.logger.warning(
                "Configuración de email incompleta. Faltan: %s. (%s)"
                % (', '.join(missing), _mail_config_summary(mail_server, mail_port, mail_use_tls, mail_use_ssl, mail_username, mail_sender, suppress_send))
            )
            return False

        # Aplicar config (útil si Flask-Mail se inicializó antes de que existieran env vars)
        current_app.config.update({
            'MAIL_SERVER': mail_server,
            'MAIL_PORT': mail_port,
            'MAIL_USE_TLS': mail_use_tls,
            'MAIL_USE_SSL': mail_use_ssl,
            'MAIL_TIMEOUT': mail_timeout,
            'MAIL_USERNAME': mail_username,
            'MAIL_PASSWORD': mail_password,
            'MAIL_DEFAULT_SENDER': mail_sender,
            'MAIL_SUPPRESS_SEND': suppress_send,
        })
        
        # Configurar Flask-Mail si no está configurado
        if not hasattr(current_app, 'extensions') or 'mail' not in current_app.extensions:
            current_app.logger.warning(
                "Flask-Mail no estaba inicializado en app.extensions; inicializando on-demand. (%s)"
                % _mail_config_summary(mail_server, mail_port, mail_use_tls, mail_use_ssl, mail_username, mail_sender, suppress_send)
            )
            mail = Mail(current_app)
        else:
            mail = current_app.extensions['mail']

        # Asegurar que el objeto Mail use la configuración actual (Mail no re-lee app.config dinámicamente)
        try:
            mail.server = mail_server
            mail.port = mail_port
            mail.use_tls = mail_use_tls
            mail.use_ssl = mail_use_ssl
            mail.username = mail_username
            mail.password = mail_password
            mail.default_sender = mail_sender
            mail.suppress_send = suppress_send
            mail.timeout = mail_timeout
        except Exception:
            pass
        
        # Crear mensaje
        asunto = f"Documento Rechazado: {nombre_archivo}"
        
        cuerpo_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #d32f2f;">Documento Rechazado</h2>
                <p>Hola {nombre_usuario},</p>
                <p>Te informamos que tu documento <strong>{nombre_archivo}</strong> ha sido rechazado.</p>
        """
        
        if comentario:
            cuerpo_html += f"""
                <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>Motivo del rechazo:</strong></p>
                    <p style="margin: 5px 0 0 0;">{comentario}</p>
                </div>
            """
        
        cuerpo_html += f"""
                <p>Por favor, ingresa a la aplicación para revisar los detalles y subir una nueva versión del documento.</p>
        """
        
        if url_archivo:
            cuerpo_html += f"""
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{url_archivo}" 
                       style="background-color: #1976d2; color: white; padding: 12px 24px; 
                              text-decoration: none; border-radius: 4px; display: inline-block;">
                        Ver Documentos
                    </a>
                </div>
            """
        
        cuerpo_html += """
                <p style="margin-top: 30px; font-size: 12px; color: #666;">
                    Este es un mensaje automático. Por favor, no respondas a este correo.
                </p>
            </div>
        </body>
        </html>
        """
        
        cuerpo_texto = f"""
Hola {nombre_usuario},

Te informamos que tu documento "{nombre_archivo}" ha sido rechazado.
        """
        
        if comentario:
            cuerpo_texto += f"\nMotivo del rechazo: {comentario}\n"
        
        cuerpo_texto += "\nPor favor, ingresa a la aplicación para revisar los detalles y subir una nueva versión del documento.\n"
        
        if url_archivo:
            cuerpo_texto += f"\nAccede aquí: {url_archivo}\n"
        
        msg = Message(
            subject=asunto,
            recipients=[destinatario],
            sender=mail_sender,
            html=cuerpo_html,
            body=cuerpo_texto
        )

        current_app.logger.info(
            "Enviando email de rechazo a %s (%s) timeout=%ss force_ipv4=%s" % (
                destinatario,
                _mail_config_summary(mail_server, mail_port, mail_use_tls, mail_use_ssl, mail_username, mail_sender, suppress_send),
                mail_timeout,
                _should_force_ipv4(),
            )
        )
        
        _send_mail_with_optional_ipv4(mail, msg, "email de rechazo")
        current_app.logger.info(f"✅ Email enviado exitosamente a {destinatario}")
        return True
        
    except Exception as e:
        current_app.logger.exception(f"❌ Error al enviar email: {e}")
        return False


def enviar_sms_rechazo(
    telefono: str,
    nombre_usuario: str,
    nombre_archivo: str,
    url_archivo: Optional[str] = None
) -> bool:
    """
    Envía un SMS notificando el rechazo de un documento usando Twilio.
    
    Returns:
        True si se envió exitosamente, False en caso contrario
    """
    if (not TWILIO_AVAILABLE) or TwilioClient is None:
        current_app.logger.warning("Twilio no está disponible. Instala con: pip install twilio")
        return False
    
    try:
        account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        twilio_phone = os.environ.get('TWILIO_PHONE_NUMBER')
        
        if not all([account_sid, auth_token, twilio_phone]):
            current_app.logger.warning("Configuración de Twilio incompleta. No se puede enviar SMS.")
            return False
        
        client = TwilioClient(account_sid, auth_token)
        
        # Limpiar número de teléfono (remover caracteres especiales)
        telefono_limpio = ''.join(filter(str.isdigit, telefono))
        if not telefono_limpio.startswith('+'):
            # Asumir código de país si no está presente (ajustar según tu país)
            codigo_pais = os.environ.get('TWILIO_DEFAULT_COUNTRY_CODE', '+1')
            telefono_limpio = f"{codigo_pais}{telefono_limpio}"
        
        # Mensaje SMS (máximo 160 caracteres recomendado)
        mensaje = f"Hola {nombre_usuario.split()[0]}, tu documento '{nombre_archivo[:30]}...' fue rechazado. "
        if url_archivo:
            mensaje += f"Revisa: {url_archivo[:50]}"
        else:
            mensaje += "Ingresa a la app para más detalles."
        
        # Truncar si es muy largo
        if len(mensaje) > 160:
            mensaje = mensaje[:157] + "..."
        
        message = client.messages.create(
            body=mensaje,
            from_=twilio_phone,
            to=telefono_limpio
        )
        
        current_app.logger.info(f"✅ SMS enviado exitosamente a {telefono_limpio} (SID: {message.sid})")
        return True
        
    except Exception as e:
        current_app.logger.error(f"❌ Error al enviar SMS: {e}")
        traceback.print_exc()
        return False


def enviar_whatsapp_rechazo(
    telefono: str,
    nombre_usuario: str,
    nombre_archivo: str,
    comentario: Optional[str] = None,
    url_archivo: Optional[str] = None
) -> bool:
    """
    Envía un mensaje de WhatsApp notificando el rechazo de un documento usando Twilio.
    
    Returns:
        True si se envió exitosamente, False en caso contrario
    """
    if (not TWILIO_AVAILABLE) or TwilioClient is None:
        current_app.logger.warning("Twilio no está disponible. Instala con: pip install twilio")
        return False
    
    try:
        account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        twilio_whatsapp = os.environ.get('TWILIO_WHATSAPP_NUMBER')  # Formato: whatsapp:+14155238886
        
        if not all([account_sid, auth_token, twilio_whatsapp]):
            current_app.logger.warning("Configuración de Twilio WhatsApp incompleta. No se puede enviar WhatsApp.")
            return False
        
        client = TwilioClient(account_sid, auth_token)
        
        # Limpiar número de teléfono
        telefono_limpio = ''.join(filter(str.isdigit, telefono))
        if not telefono_limpio.startswith('+'):
            codigo_pais = os.environ.get('TWILIO_DEFAULT_COUNTRY_CODE', '+1')
            telefono_limpio = f"whatsapp:{codigo_pais}{telefono_limpio}"
        else:
            telefono_limpio = f"whatsapp:{telefono_limpio}"
        
        # Mensaje WhatsApp (más largo que SMS)
        mensaje = f"🔴 *Documento Rechazado*\n\n"
        mensaje += f"Hola {nombre_usuario.split()[0]},\n\n"
        mensaje += f"Tu documento *{nombre_archivo}* ha sido rechazado.\n\n"
        
        if comentario:
            mensaje += f"*Motivo:* {comentario}\n\n"
        
        mensaje += "Por favor, ingresa a la aplicación para revisar los detalles y subir una nueva versión.\n"
        
        if url_archivo:
            mensaje += f"\n🔗 {url_archivo}"
        
        message = client.messages.create(
            body=mensaje,
            from_=twilio_whatsapp,
            to=telefono_limpio
        )
        
        current_app.logger.info(f"✅ WhatsApp enviado exitosamente a {telefono_limpio} (SID: {message.sid})")
        return True
        
    except Exception as e:
        current_app.logger.error(f"❌ Error al enviar WhatsApp: {e}")
        traceback.print_exc()
        return False

