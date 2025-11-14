 """
Módulo para enviar notificaciones externas (Email, SMS, WhatsApp)
cuando se rechaza un documento o cambia su estado.
"""
import os
from typing import Optional, Dict, List
from flask import current_app
from app.models import User, Archivo
import traceback

# Intentar importar dependencias opcionales
try:
    from flask_mail import Mail, Message
    FLASK_MAIL_AVAILABLE = True
except ImportError:
    FLASK_MAIL_AVAILABLE = False

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False


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
        app_url = os.environ.get('APP_URL', 'http://localhost:5000')
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
    if not FLASK_MAIL_AVAILABLE:
        current_app.logger.warning("Flask-Mail no está disponible. Instala con: pip install flask-mail")
        return False
    
    try:
        # Obtener configuración de email desde variables de entorno o config
        mail_server = os.environ.get('MAIL_SERVER') or current_app.config.get('MAIL_SERVER')
        mail_port = int(os.environ.get('MAIL_PORT') or current_app.config.get('MAIL_PORT', 587))
        mail_use_tls = (os.environ.get('MAIL_USE_TLS', 'true') or 
                       str(current_app.config.get('MAIL_USE_TLS', True))).lower() == 'true'
        mail_username = os.environ.get('MAIL_USERNAME') or current_app.config.get('MAIL_USERNAME')
        mail_password = os.environ.get('MAIL_PASSWORD') or current_app.config.get('MAIL_PASSWORD')
        mail_sender = (os.environ.get('MAIL_DEFAULT_SENDER') or 
                      current_app.config.get('MAIL_DEFAULT_SENDER') or 
                      mail_username)
        
        # Verificar configuración mínima
        if not all([mail_server, mail_username, mail_password]):
            current_app.logger.warning(
                "Configuración de email incompleta. Configura MAIL_SERVER, MAIL_USERNAME y MAIL_PASSWORD."
            )
            return False
        
        # Configurar Flask-Mail si no está configurado
        if not hasattr(current_app, 'extensions') or 'mail' not in current_app.extensions:
            # Actualizar configuración temporalmente
            temp_config = {
                'MAIL_SERVER': mail_server,
                'MAIL_PORT': mail_port,
                'MAIL_USE_TLS': mail_use_tls,
                'MAIL_USERNAME': mail_username,
                'MAIL_PASSWORD': mail_password,
                'MAIL_DEFAULT_SENDER': mail_sender
            }
            current_app.config.update(temp_config)
            mail = Mail(current_app)
        else:
            mail = current_app.extensions['mail']
        
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
            html=cuerpo_html,
            body=cuerpo_texto
        )
        
        mail.send(msg)
        current_app.logger.info(f"✅ Email enviado exitosamente a {destinatario}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"❌ Error al enviar email: {e}")
        traceback.print_exc()
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
    if not TWILIO_AVAILABLE:
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
    if not TWILIO_AVAILABLE:
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

