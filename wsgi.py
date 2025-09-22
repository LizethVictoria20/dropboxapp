#!/usr/bin/env python3
"""
WSGI entry point para producción
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Cargar variables de entorno desde .env con ruta absoluta (robusto en servidor)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / '.env')

# Configurar el entorno como producción
os.environ.setdefault('FLASK_ENV', 'production')

from app import create_app

application = create_app('production')

if __name__ == "__main__":
    application.run() 