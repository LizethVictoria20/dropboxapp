#!/usr/bin/env python3
"""
Script para crear datos de ejemplo para el dashboard
"""
import os
import sys
from datetime import datetime, timedelta
import random

# Agregar el directorio del proyecto al path de Python
sys.path.insert(0, os.path.abspath('.'))

from app import create_app, db
from app.models import User, Archivo, UserActivityLog, Folder

def create_sample_data():
    """Crear datos de ejemplo para el dashboard"""
    app = create_app()
    
    with app.app_context():
        print("🔄 Creando datos de ejemplo para el dashboard...")
        
        # Crear usuarios de ejemplo si no existen
        sample_users = []
        
        # Verificar si ya hay usuarios
        existing_users = User.query.filter(User.email.like('%@example.com')).all()
        if not existing_users:
            users_data = [
                {'email': 'admin@example.com', 'nombre': 'Admin', 'apellido': 'Sistema', 'rol': 'admin'},
                {'email': 'cliente1@example.com', 'nombre': 'Juan', 'apellido': 'Pérez', 'rol': 'cliente'},
                {'email': 'cliente2@example.com', 'nombre': 'María', 'apellido': 'García', 'rol': 'cliente'},
                {'email': 'cliente3@example.com', 'nombre': 'Carlos', 'apellido': 'López', 'rol': 'cliente'},
                {'email': 'lector@example.com', 'nombre': 'Ana', 'apellido': 'Martínez', 'rol': 'lector'},
            ]
            
            for user_data in users_data:
                user = User()
                user.email = user_data['email']
                user.nombre = user_data['nombre']
                user.apellido = user_data['apellido']
                user.rol = user_data['rol']
                user.set_password('123456')  # Contraseña de ejemplo
                
                # Fechas de registro variadas en los últimos 6 meses
                days_ago = random.randint(1, 180)
                user.fecha_registro = datetime.utcnow() - timedelta(days=days_ago)
                
                db.session.add(user)
                sample_users.append(user)
            
            db.session.commit()
            print(f"✅ Creados {len(users_data)} usuarios de ejemplo")
        else:
            sample_users = existing_users
            print("ℹ️  Usando usuarios existentes")
        
        # Obtener todos los usuarios para crear datos
        all_users = User.query.all()
        
        # Crear carpetas de ejemplo
        folders_count = Folder.query.count()
        if folders_count < 10:
            for i in range(10):
                folder = Folder()
                folder.name = f"Carpeta de Ejemplo {i+1}"
                folder.user_id = random.choice(all_users).id
                folder.dropbox_path = f"/ejemplo/carpeta_{i+1}"
                
                # Fechas de creación variadas
                days_ago = random.randint(1, 90)
                folder.fecha_creacion = datetime.utcnow() - timedelta(days=days_ago)
                
                db.session.add(folder)
            
            db.session.commit()
            print("✅ Creadas carpetas de ejemplo")
        
        # Crear archivos de ejemplo
        archivos_count = Archivo.query.count()
        if archivos_count < 30:
            file_extensions = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'png', 'txt', 'zip', 'json']
            file_categories = ['Documentos', 'Imágenes', 'Contratos', 'Reportes', 'Personal']
            
            for i in range(50):
                archivo = Archivo()
                archivo.nombre = f"archivo_ejemplo_{i+1}"
                ext = random.choice(file_extensions)
                archivo.extension = ext
                archivo.categoria = random.choice(file_categories)
                archivo.subcategoria = f"Sub-{archivo.categoria}"
                archivo.dropbox_path = f"/ejemplo/archivos/archivo_ejemplo_{i+1}.{ext}"
                archivo.usuario_id = random.choice(all_users).id
                archivo.tamano = random.randint(1024, 5000000)  # Entre 1KB y 5MB
                
                # Fechas de subida variadas en los últimos 3 meses
                days_ago = random.randint(1, 90)
                hours_ago = random.randint(0, 23)
                archivo.fecha_subida = datetime.utcnow() - timedelta(days=days_ago, hours=hours_ago)
                
                db.session.add(archivo)
            
            db.session.commit()
            print("✅ Creados archivos de ejemplo")
        
        # Crear actividades de ejemplo
        activities_count = UserActivityLog.query.count()
        if activities_count < 50:
            actions = [
                'login', 'logout', 'upload_file', 'create_folder', 'view_dashboard',
                'edit_profile', 'delete_file', 'share_folder', 'download_file'
            ]
            
            for i in range(100):
                activity = UserActivityLog()
                activity.user_id = random.choice(all_users).id
                activity.accion = random.choice(actions)
                activity.descripcion = f"Actividad de ejemplo {i+1}"
                activity.ip_address = f"192.168.1.{random.randint(1, 255)}"
                
                # Fechas de actividad variadas en los últimos 30 días
                days_ago = random.randint(0, 30)
                hours_ago = random.randint(0, 23)
                minutes_ago = random.randint(0, 59)
                activity.fecha = datetime.utcnow() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
                
                db.session.add(activity)
            
            db.session.commit()
            print("✅ Creadas actividades de ejemplo")
        
        # Crear algunos beneficiarios
        beneficiarios_count = User.query.filter_by(es_beneficiario=True).count()
        if beneficiarios_count < 5:
            # Seleccionar algunos usuarios como beneficiarios
            clientes = User.query.filter_by(rol='cliente').all()
            if clientes:
                for i in range(min(3, len(clientes))):
                    cliente = clientes[i]
                    
                    # Crear un beneficiario para este cliente
                    beneficiario = User()
                    beneficiario.email = f"beneficiario{i+1}@example.com"
                    beneficiario.nombre = f"Beneficiario"
                    beneficiario.apellido = f"Ejemplo {i+1}"
                    beneficiario.es_beneficiario = True
                    beneficiario.titular_id = cliente.id
                    beneficiario.rol = 'cliente'
                    beneficiario.set_password('123456')
                    
                    days_ago = random.randint(1, 60)
                    beneficiario.fecha_registro = datetime.utcnow() - timedelta(days=days_ago)
                    
                    db.session.add(beneficiario)
                
                db.session.commit()
                print("✅ Creados beneficiarios de ejemplo")
        
        print("\n🎉 ¡Datos de ejemplo creados exitosamente!")
        print("\n📊 Resumen de datos:")
        print(f"   👥 Usuarios: {User.query.count()}")
        print(f"   📁 Carpetas: {Folder.query.count()}")
        print(f"   📄 Archivos: {Archivo.query.count()}")
        print(f"   📈 Actividades: {UserActivityLog.query.count()}")
        print(f"   👨‍👩‍👧‍👦 Beneficiarios: {User.query.filter_by(es_beneficiario=True).count()}")
        
        print("\n🔑 Credenciales de acceso:")
        print("   Email: admin@example.com")
        print("   Contraseña: 123456")
        print("\n   Puedes acceder al dashboard admin en: http://localhost:5000/dashboard/admin")

if __name__ == '__main__':
    create_sample_data() 