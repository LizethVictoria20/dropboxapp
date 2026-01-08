#!/usr/bin/env python3
"""
WSGI entry point para producción
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Cargar variables de entorno desde .env con ruta absoluta (robusto en servidor).
# Nota: este archivo vive en la raíz del proyecto, por lo que el .env esperado
# está en el mismo directorio.
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'
if not env_path.exists():
    # Fallback defensivo por si el proyecto se ejecuta desde otra estructura.
    alt_env_path = BASE_DIR.parent / '.env'
    env_path = alt_env_path if alt_env_path.exists() else env_path

load_dotenv(dotenv_path=env_path)

# Configurar el entorno como producción
os.environ.setdefault('FLASK_ENV', 'production')

from app import create_app

application = create_app('production')

if __name__ == "__main__":
    application.run() 