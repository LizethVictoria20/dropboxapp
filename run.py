import argparse
from dotenv import load_dotenv

# Cargar variables de entorno desde .env ANTES de importar la app
load_dotenv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Flask application')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the server on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to run the server on')
    args = parser.parse_args()
    
    app.run(debug=True, host=args.host, port=args.port) 