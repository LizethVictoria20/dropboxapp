#!/usr/bin/env python3
"""
Script para configurar las variables de entorno de Dropbox
"""
import os
import sys
from pathlib import Path

def check_current_env():
    """Verifica las variables de entorno actuales"""
    print("🔍 Verificando variables de entorno actuales...")
    print("=" * 50)
    
    variables = [
        'DROPBOX_API_KEY',
        'DROPBOX_APP_KEY', 
        'DROPBOX_APP_SECRET',
        'DROPBOX_ACCESS_TOKEN'
    ]
    
    for var in variables:
        value = os.environ.get(var)
        if value:
            # Mostrar solo los primeros 10 caracteres por seguridad
            display_value = value[:10] + "..." if len(value) > 10 else value
            print(f"✅ {var}: {display_value}")
        else:
            print(f"❌ {var}: No configurada")
    
    print()

def create_env_file():
    """Crea un archivo .env de ejemplo"""
    env_content = """# Configuración de Dropbox
# Obtén estas credenciales desde: https://www.dropbox.com/developers/apps

# Token de acceso de la API de Dropbox (OBLIGATORIO)
DROPBOX_API_KEY=tu_api_key_aqui

# Clave de la aplicación de Dropbox
DROPBOX_APP_KEY=tu_app_key_aqui

# Secreto de la aplicación de Dropbox  
DROPBOX_APP_SECRET=tu_app_secret_aqui

# Token de acceso de Dropbox
DROPBOX_ACCESS_TOKEN=tu_access_token_aqui

# Otras configuraciones
SECRET_KEY=tu_secret_key_aqui
DATABASE_URL=sqlite:///app.db
"""
    
    env_file = Path('.env')
    if env_file.exists():
        print("⚠️  El archivo .env ya existe. ¿Quieres sobrescribirlo? (y/N): ", end="")
        response = input().strip().lower()
        if response != 'y':
            print("Operación cancelada.")
            return
    
    try:
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✅ Archivo .env creado exitosamente")
        print("📝 Edita el archivo .env con tus credenciales reales de Dropbox")
    except Exception as e:
        print(f"❌ Error creando archivo .env: {e}")

def show_instructions():
    """Muestra instrucciones para obtener credenciales"""
    print("\n📋 INSTRUCCIONES PARA OBTENER CREDENCIALES DE DROPBOX")
    print("=" * 60)
    print("1. Ve a https://www.dropbox.com/developers/apps")
    print("2. Crea una nueva aplicación o selecciona una existente")
    print("3. En la sección 'OAuth 2', genera un token de acceso")
    print("4. Copia las credenciales y configúralas en tu servidor")
    print("\n📝 CONFIGURACIÓN EN PRODUCCIÓN:")
    print("=" * 40)
    print("En tu servidor de producción, ejecuta:")
    print()
    print("export DROPBOX_API_KEY='tu_api_key_aqui'")
    print("export DROPBOX_APP_KEY='tu_app_key_aqui'")
    print("export DROPBOX_APP_SECRET='tu_app_secret_aqui'")
    print("export DROPBOX_ACCESS_TOKEN='tu_access_token_aqui'")
    print()
    print("O agrega estas líneas a tu archivo de configuración del servidor web.")

def test_connection():
    """Prueba la conexión con Dropbox"""
    print("\n🧪 Probando conexión con Dropbox...")
    
    api_key = os.environ.get('DROPBOX_API_KEY')
    if not api_key:
        print("❌ DROPBOX_API_KEY no está configurada")
        return False
    
    try:
        import dropbox
        dbx = dropbox.Dropbox(api_key)
        account = dbx.users_get_current_account()
        print(f"✅ Conexión exitosa!")
        print(f"   Conectado como: {account.email}")
        print(f"   Nombre: {account.name.display_name}")
        print(f"   País: {account.country}")
        return True
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return False

def main():
    """Función principal"""
    print("🚀 Configurador de Variables de Entorno - Dropbox")
    print("=" * 55)
    
    while True:
        print("\nOpciones disponibles:")
        print("1. Verificar variables actuales")
        print("2. Crear archivo .env de ejemplo")
        print("3. Mostrar instrucciones")
        print("4. Probar conexión con Dropbox")
        print("5. Salir")
        
        choice = input("\nSelecciona una opción (1-5): ").strip()
        
        if choice == '1':
            check_current_env()
        elif choice == '2':
            create_env_file()
        elif choice == '3':
            show_instructions()
        elif choice == '4':
            test_connection()
        elif choice == '5':
            print("👋 ¡Hasta luego!")
            break
        else:
            print("❌ Opción inválida. Intenta de nuevo.")

if __name__ == "__main__":
    main() 