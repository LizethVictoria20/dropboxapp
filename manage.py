#!/usr/bin/env python3
"""
Script de gestión para la aplicación Flask
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from app import create_app

# Cargar variables desde .env (ruta absoluta) para modo local/CLI
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    # Fallback: buscar .env en el cwd
    try:
        load_dotenv()
    except Exception:
        pass

def main():
    """Función principal para ejecutar la aplicación"""
    app = create_app()
    
    if len(sys.argv) > 1 and sys.argv[1] == 'run':
        # Ejecutar en modo desarrollo
        app.run(
            host='0.0.0.0',
            port=5001,
            debug=True,
            use_reloader=True
        )
    elif len(sys.argv) > 1 and sys.argv[1] == 'shell':
        # Ejecutar shell interactivo
        from flask.cli import with_appcontext
        with app.app_context():
            import code
            code.interact(local=locals())
    else:
        print("Uso: python manage.py [run|shell]")
        print("  run   - Ejecutar servidor de desarrollo")
        print("  shell - Ejecutar shell interactivo")

if __name__ == '__main__':
    main()
