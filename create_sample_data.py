#!/usr/bin/env python3
"""
Script para crear datos de muestra para el sistema mydropboxapp
Ejecutar con: python create_sample_data.py
"""

import os
import sys
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

# Configurar el path para importar la app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configurar SQLite para desarrollo
os.environ['DATABASE_URL'] = 'sqlite:///mydropboxapp.db'

from app import create_app, db
from app.models import User, Folder, Archivo, UserActivityLog, Notification, SystemSettings

def create_sample_data():
    """Crear datos de muestra para el sistema"""
    
    app = create_app()
    
    with app.app_context():
        # Eliminar datos existentes
        print("🗑️  Limpiando datos existentes...")
        db.drop_all()
        db.create_all()
        
        # Crear configuraciones del sistema
        print("⚙️  Creando configuraciones del sistema...")
        settings = [
            SystemSettings(clave="site_name", valor="MyDropboxApp", descripcion="Nombre del sitio"),
            SystemSettings(clave="max_file_size", valor="50MB", descripcion="Tamaño máximo de archivo"),
            SystemSettings(clave="allowed_extensions", valor="pdf,doc,docx,jpg,png", descripcion="Extensiones permitidas"),
        ]
        for setting in settings:
            db.session.add(setting)
        
        # Crear usuarios de muestra
        print("👥 Creando usuarios de muestra...")
        
        # Super Admin
        superadmin = User(
            email="superadmin@mydropboxapp.com",
            nombre="María",
            apellido="Rodríguez",
            telefono="+34 600 123 456",
            ciudad="Madrid",
            estado="Madrid",
            direccion="Calle Gran Vía 123",
            codigo_postal="28013",
            fecha_nacimiento=datetime(1985, 5, 15).date(),
            rol="superadmin",
            activo=True,
            fecha_registro=datetime.utcnow() - timedelta(days=365),
            dropbox_folder_path="/superadmin@mydropboxapp.com"
        )
        superadmin.set_password("superadmin123")
        db.session.add(superadmin)
        
        # Admin
        admin = User(
            email="admin@mydropboxapp.com", 
            nombre="Carlos",
            apellido="García",
            telefono="+34 600 654 321",
            ciudad="Barcelona",
            estado="Cataluña",
            direccion="Passeig de Gràcia 456",
            codigo_postal="08008",
            fecha_nacimiento=datetime(1990, 8, 22).date(),
            rol="admin",
            activo=True,
            fecha_registro=datetime.utcnow() - timedelta(days=200),
            dropbox_folder_path="/admin@mydropboxapp.com"
        )
        admin.set_password("admin123")
        db.session.add(admin)
        
        # Cliente activo
        cliente1 = User(
            email="cliente1@example.com",
            nombre="Ana",
            apellido="López",
            telefono="+34 600 789 123",
            ciudad="Valencia",
            estado="Valencia",
            direccion="Avenida del Puerto 789",
            codigo_postal="46023",
            fecha_nacimiento=datetime(1992, 12, 10).date(),
            rol="cliente",
            activo=True,
            fecha_registro=datetime.utcnow() - timedelta(days=90),
            dropbox_folder_path="/cliente1@example.com"
        )
        cliente1.set_password("cliente123")
        db.session.add(cliente1)
        
        # Cliente con más datos
        cliente2 = User(
            email="cliente2@example.com",
            nombre="José",
            apellido="Martínez",
            telefono="+34 600 456 789",
            ciudad="Sevilla", 
            estado="Andalucía",
            direccion="Calle Sierpes 321",
            codigo_postal="41004",
            fecha_nacimiento=datetime(1988, 3, 5).date(),
            rol="cliente",
            activo=True,
            fecha_registro=datetime.utcnow() - timedelta(days=45),
            dropbox_folder_path="/cliente2@example.com"
        )
        cliente2.set_password("cliente123")
        db.session.add(cliente2)
        
        # Lector
        lector = User(
            email="lector@mydropboxapp.com",
            nombre="Elena",
            apellido="Fernández",
            telefono="+34 600 321 654",
            ciudad="Bilbao",
            estado="País Vasco",
            rol="lector",
            activo=True,
            fecha_registro=datetime.utcnow() - timedelta(days=30),
            dropbox_folder_path="/lector@mydropboxapp.com"
        )
        lector.set_password("lector123")
        db.session.add(lector)
        
        # Cliente inactivo para testing
        cliente_inactivo = User(
            email="inactivo@example.com",
            nombre="Pedro",
            apellido="Sánchez",
            rol="cliente",
            activo=False,
            fecha_registro=datetime.utcnow() - timedelta(days=180),
            dropbox_folder_path="/inactivo@example.com"
        )
        cliente_inactivo.set_password("cliente123")
        db.session.add(cliente_inactivo)
        
        db.session.commit()
        print(f"✅ Creados {User.query.count()} usuarios")
        
        # Crear carpetas de muestra
        print("📁 Creando carpetas de muestra...")
        carpetas = [
            Folder(name="Documentos Personales", user_id=cliente1.id, 
                  dropbox_path=f"{cliente1.dropbox_folder_path}/Documentos_Personales", es_publica=True),
            Folder(name="Contratos", user_id=cliente1.id, 
                  dropbox_path=f"{cliente1.dropbox_folder_path}/Contratos", es_publica=False),
            Folder(name="Facturas 2024", user_id=cliente2.id, 
                  dropbox_path=f"{cliente2.dropbox_folder_path}/Facturas_2024", es_publica=True),
            Folder(name="Proyectos", user_id=cliente2.id, 
                  dropbox_path=f"{cliente2.dropbox_folder_path}/Proyectos", es_publica=True),
            Folder(name="Certificados", user_id=cliente2.id, 
                  dropbox_path=f"{cliente2.dropbox_folder_path}/Certificados", es_publica=False),
        ]
        for carpeta in carpetas:
            db.session.add(carpeta)
        
        db.session.commit()
        print(f"✅ Creadas {Folder.query.count()} carpetas")
        
        # Crear archivos de muestra
        print("📄 Creando archivos de muestra...")
        archivos = [
            Archivo(nombre="DNI_Ana_Lopez.pdf", categoria="Personal", subcategoria="Documentos de identidad",
                   dropbox_path=f"{cliente1.dropbox_folder_path}/Documentos_Personales/DNI_Ana_Lopez.pdf",
                   usuario_id=cliente1.id, tamano=2048000, extension="pdf"),
            Archivo(nombre="Contrato_Trabajo_2024.pdf", categoria="Laboral", subcategoria="Contratos laborales",
                   dropbox_path=f"{cliente1.dropbox_folder_path}/Contratos/Contrato_Trabajo_2024.pdf",
                   usuario_id=cliente1.id, tamano=1536000, extension="pdf"),
            Archivo(nombre="Factura_Enero_2024.pdf", categoria="Finanzas", subcategoria="Facturas",
                   dropbox_path=f"{cliente2.dropbox_folder_path}/Facturas_2024/Factura_Enero_2024.pdf",
                   usuario_id=cliente2.id, tamano=512000, extension="pdf"),
            Archivo(nombre="Propuesta_Proyecto_A.docx", categoria="Laboral", subcategoria="Documentos técnicos",
                   dropbox_path=f"{cliente2.dropbox_folder_path}/Proyectos/Propuesta_Proyecto_A.docx",
                   usuario_id=cliente2.id, tamano=3072000, extension="docx"),
            Archivo(nombre="Certificado_Formacion.pdf", categoria="Educación", subcategoria="Certificados de estudios",
                   dropbox_path=f"{cliente2.dropbox_folder_path}/Certificados/Certificado_Formacion.pdf",
                   usuario_id=cliente2.id, tamano=1024000, extension="pdf"),
        ]
        for archivo in archivos:
            db.session.add(archivo)
        
        db.session.commit()
        print(f"✅ Creados {Archivo.query.count()} archivos")
        
        # Crear logs de actividad
        print("📊 Creando logs de actividad...")
        actividades = []
        
        # Actividades del superadmin
        actividades.extend([
            UserActivityLog(user_id=superadmin.id, accion="login", 
                          descripcion="Inicio de sesión desde 192.168.1.100",
                          fecha=datetime.utcnow() - timedelta(hours=2)),
            UserActivityLog(user_id=superadmin.id, accion="user_created",
                          descripcion="Usuario admin@mydropboxapp.com creado con rol admin",
                          fecha=datetime.utcnow() - timedelta(days=1)),
        ])
        
        # Actividades del admin
        actividades.extend([
            UserActivityLog(user_id=admin.id, accion="login",
                          descripcion="Inicio de sesión desde 192.168.1.200",
                          fecha=datetime.utcnow() - timedelta(hours=1)),
            UserActivityLog(user_id=admin.id, accion="dashboard_access",
                          descripcion="Acceso al dashboard administrativo",
                          fecha=datetime.utcnow() - timedelta(minutes=30)),
        ])
        
        # Actividades de clientes
        for i, cliente in enumerate([cliente1, cliente2], 1):
            actividades.extend([
                UserActivityLog(user_id=cliente.id, accion="user_registered",
                              descripcion=f"Usuario registrado desde 192.168.1.{100+i}",
                              fecha=cliente.fecha_registro),
                UserActivityLog(user_id=cliente.id, accion="login",
                              descripcion=f"Inicio de sesión desde 192.168.1.{100+i}",
                              fecha=datetime.utcnow() - timedelta(hours=3-i)),
                UserActivityLog(user_id=cliente.id, accion="upload",
                              descripcion="Archivo subido correctamente",
                              fecha=datetime.utcnow() - timedelta(days=i)),
                UserActivityLog(user_id=cliente.id, accion="create_folder",
                              descripcion="Nueva carpeta creada",
                              fecha=datetime.utcnow() - timedelta(days=i*2)),
            ])
        
        for actividad in actividades:
            db.session.add(actividad)
        
        db.session.commit()
        print(f"✅ Creados {UserActivityLog.query.count()} logs de actividad")
        
        # Crear notificaciones
        print("🔔 Creando notificaciones...")
        notificaciones = [
            Notification(user_id=cliente1.id, titulo="Bienvenido al sistema",
                        mensaje="¡Gracias por registrarte! Explora todas las funcionalidades disponibles.",
                        tipo="info", leida=False),
            Notification(user_id=cliente1.id, titulo="Archivo subido correctamente",
                        mensaje="Tu archivo 'DNI_Ana_Lopez.pdf' se ha subido exitosamente.",
                        tipo="success", leida=True, fecha_leida=datetime.utcnow() - timedelta(hours=1)),
            Notification(user_id=cliente2.id, titulo="Nueva carpeta creada",
                        mensaje="La carpeta 'Facturas 2024' se ha creado correctamente.",
                        tipo="success", leida=False),
            Notification(user_id=cliente2.id, titulo="Actualiza tu perfil", 
                        mensaje="Completa tu información personal para una mejor experiencia.",
                        tipo="warning", leida=False),
            Notification(user_id=admin.id, titulo="Nuevos usuarios registrados",
                        mensaje="Se han registrado 2 nuevos usuarios esta semana.",
                        tipo="info", leida=False),
        ]
        for notificacion in notificaciones:
            db.session.add(notificacion)
        
        db.session.commit()
        print(f"✅ Creadas {Notification.query.count()} notificaciones")
        
        # Actualizar último acceso de algunos usuarios
        print("🕒 Actualizando últimos accesos...")
        cliente1.ultimo_acceso = datetime.utcnow() - timedelta(hours=3)
        cliente2.ultimo_acceso = datetime.utcnow() - timedelta(hours=1)
        admin.ultimo_acceso = datetime.utcnow() - timedelta(minutes=30)
        superadmin.ultimo_acceso = datetime.utcnow() - timedelta(hours=2)
        
        db.session.commit()
        
        print("\n🎉 ¡Datos de muestra creados exitosamente!")
        print("\n📋 Resumen de usuarios creados:")
        print(f"   👑 Super Admin: superadmin@mydropboxapp.com (contraseña: superadmin123)")
        print(f"   🛡️  Admin: admin@mydropboxapp.com (contraseña: admin123)")
        print(f"   👤 Cliente 1: cliente1@example.com (contraseña: cliente123)")
        print(f"   👤 Cliente 2: cliente2@example.com (contraseña: cliente123)")
        print(f"   👁️  Lector: lector@mydropboxapp.com (contraseña: lector123)")
        print(f"   ❌ Inactivo: inactivo@example.com (contraseña: cliente123)")
        
        print(f"\n📊 Estadísticas:")
        print(f"   • {User.query.count()} usuarios")
        print(f"   • {Folder.query.count()} carpetas")
        print(f"   • {Archivo.query.count()} archivos")
        print(f"   • {UserActivityLog.query.count()} logs de actividad")
        print(f"   • {Notification.query.count()} notificaciones")
        
        print(f"\n🚀 Para probar el sistema:")
        print(f"   1. Ejecuta: DATABASE_URL='sqlite:///mydropboxapp.db' flask run")
        print(f"   2. Ve a http://127.0.0.1:5000/auth/")
        print(f"   3. Inicia sesión con cualquiera de los usuarios de arriba")
        print(f"   4. Explora los diferentes dashboards según el rol")

if __name__ == "__main__":
    create_sample_data() 