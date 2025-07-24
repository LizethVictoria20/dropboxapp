#!/usr/bin/env python3
"""
WSGI entry point para producción
"""
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar el entorno como producción
os.environ.setdefault('FLASK_ENV', 'production')

from app import create_app

application = create_app('production')

if __name__ == "__main__":
    application.run() 