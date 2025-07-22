#!/usr/bin/env python3
"""
Script para verificar usuarios en la base de datos
"""

import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar Flask
os.environ.setdefault('FLASK_ENV', 'development')

from app import create_app, db
from app.models import User

def check_users():
    """Verifica los usuarios en la base de datos"""
    app = create_app()
    
    with app.app_context():
        users = User.query.all()
        
        print("=== USUARIOS EN LA BASE DE DATOS ===")
        print(f"Total de usuarios: {len(users)}")
        
        for i, user in enumerate(users, 1):
            print(f"\n{i}. ID: {user.id}")
            print(f"   Email: {user.email}")
            print(f"   Nombre: {user.nombre or 'No especificado'}")
            print(f"   Rol: {user.rol}")
            print(f"   Dropbox folder path: {user.dropbox_folder_path or 'No configurado'}")
            print(f"   Fecha de registro: {user.fecha_registro}")

if __name__ == "__main__":
    check_users() 