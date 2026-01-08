import argparse
from dotenv import load_dotenv
from pathlib import Path

# Cargar variables de entorno desde .env ANTES de importar la app
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path if env_path.exists() else None)

from app import create_app

app = create_app()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Flask application')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the server on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to run the server on')
    args = parser.parse_args()
    
    app.run(debug=True, host=args.host, port=args.port) 