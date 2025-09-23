#!/usr/bin/env python3
"""
Script para generar un refresh token de Dropbox
Esto permitirá la renovación automática de tokens de acceso

Ejecuta este script cuando necesites un nuevo refresh token
"""

import os
import requests
import json
import webbrowser
import urllib.parse
from dotenv import load_dotenv
import argparse
from datetime import datetime

# Cargar variables de entorno
load_dotenv()

def get_dropbox_credentials():
    """Obtiene las credenciales de Dropbox desde variables de entorno"""
    app_key = os.environ.get('DROPBOX_APP_KEY')
    app_secret = os.environ.get('DROPBOX_APP_SECRET')
    
    if not app_key or not app_secret:
        print("❌ Error: DROPBOX_APP_KEY y DROPBOX_APP_SECRET deben estar configuradas")
        print("\nAgrega estas variables a tu archivo .env:")
        print("DROPBOX_APP_KEY=tu_app_key_aqui")
        print("DROPBOX_APP_SECRET=tu_app_secret_aqui")
        return None, None
    
    return app_key, app_secret

def generate_authorization_url(app_key):
    """Genera la URL de autorización de Dropbox"""
    base_url = "https://www.dropbox.com/oauth2/authorize"
    params = {
        'client_id': app_key,
        'response_type': 'code',
        'token_access_type': 'offline'  # Para obtener refresh token
    }
    
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    return url

def exchange_code_for_tokens(app_key, app_secret, authorization_code):
    """Intercambia el código de autorización por tokens"""
    url = "https://api.dropboxapi.com/oauth2/token"
    
    data = {
        'code': authorization_code,
        'grant_type': 'authorization_code',
        'client_id': app_key,
        'client_secret': app_secret
    }
    
    try:
        response = requests.post(url, data=data, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Error en la petición: {response.status_code}")
            print(f"Respuesta: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return None

def save_tokens_to_env(access_token, refresh_token):
    """Guarda los tokens en el archivo .env"""
    env_file = '.env'
    
    # Leer archivo .env actual
    env_content = []
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            env_content = f.readlines()
    
    # Actualizar o agregar tokens
    access_token_found = False
    refresh_token_found = False
    
    for i, line in enumerate(env_content):
        if line.startswith('DROPBOX_ACCESS_TOKEN='):
            env_content[i] = f'DROPBOX_ACCESS_TOKEN={access_token}\n'
            access_token_found = True
        elif line.startswith('DROPBOX_REFRESH_TOKEN='):
            env_content[i] = f'DROPBOX_REFRESH_TOKEN={refresh_token}\n'
            refresh_token_found = True
    
    # Agregar tokens si no se encontraron
    if not access_token_found:
        env_content.append(f'DROPBOX_ACCESS_TOKEN={access_token}\n')
    if not refresh_token_found:
        env_content.append(f'DROPBOX_REFRESH_TOKEN={refresh_token}\n')
    
    # Escribir archivo actualizado
    with open(env_file, 'w') as f:
        f.writelines(env_content)
    
    print(f"✅ Tokens guardados en {env_file}")

def save_tokens_to_cache_file(access_token, refresh_token):
    """Guarda tokens también en .dropbox_tokens.json para que el gestor los use como fallback"""
    data = {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'last_refresh': datetime.now().isoformat()
    }
    try:
        with open('.dropbox_tokens.json', 'w') as f:
            json.dump(data, f, indent=2)
        print("✅ Tokens guardados en .dropbox_tokens.json")
    except Exception as e:
        print(f"⚠️ No se pudo guardar .dropbox_tokens.json: {e}")

def test_tokens(access_token):
    """Prueba que el access token funciona"""
    url = "https://api.dropboxapi.com/2/users/get_current_account"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            user_info = response.json()
            print(f"✅ Token válido. Usuario: {user_info.get('email', 'N/A')}")
            return True
        else:
            print(f"❌ Error probando token: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error probando token: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Generador de Refresh Token de Dropbox")
    parser.add_argument('--code', help='Código de autorización devuelto por Dropbox (para modo no interactivo)')
    parser.add_argument('--no-browser', action='store_true', help='No intentar abrir el navegador automáticamente')
    args = parser.parse_args()
    print("🔄 Generador de Refresh Token de Dropbox")
    print("=" * 50)
    
    # Paso 1: Obtener credenciales
    app_key, app_secret = get_dropbox_credentials()
    if not app_key or not app_secret:
        return
    
    print(f"✅ Credenciales encontradas")
    print(f"App Key: {app_key[:10]}...")
    
    # Paso 2: Generar URL de autorización
    auth_url = generate_authorization_url(app_key)
    
    print(f"\n📋 Paso 1: Autorizar la aplicación")
    print(f"URL: {auth_url}")
    
    # Abrir navegador automáticamente (a menos que se pida lo contrario)
    if not args.no_browser:
        try:
            webbrowser.open(auth_url)
        except:
            print("No se pudo abrir el navegador automáticamente")
            print("Copia y pega la URL en tu navegador")
    
    # Paso 3: Obtener código de autorización
    print(f"\n📋 Paso 2: Obtener código de autorización")
    print("1. Inicia sesión en Dropbox si es necesario")
    print("2. Autoriza la aplicación")
    print("3. Copia el código que aparece en la página")
    
    authorization_code = args.code.strip() if args.code else input("\n🔑 Pega el código de autorización aquí: ").strip()
    
    if not authorization_code:
        print("❌ Error: No se proporcionó código de autorización")
        return
    
    # Paso 4: Intercambiar código por tokens
    print(f"\n📋 Paso 3: Obteniendo tokens...")
    token_data = exchange_code_for_tokens(app_key, app_secret, authorization_code)
    
    if not token_data:
        print("❌ Error: No se pudieron obtener los tokens")
        return
    
    access_token = token_data.get('access_token')
    refresh_token = token_data.get('refresh_token')
    
    if not access_token or not refresh_token:
        print("❌ Error: Los tokens recibidos están incompletos")
        print(f"Respuesta: {json.dumps(token_data, indent=2)}")
        return
    
    print("✅ Tokens obtenidos exitosamente")
    
    # Paso 5: Probar tokens
    print(f"\n📋 Paso 4: Probando tokens...")
    if not test_tokens(access_token):
        print("⚠️ Advertencia: Los tokens podrían no funcionar correctamente")
    
    # Paso 6: Guardar tokens
    print(f"\n📋 Paso 5: Guardando tokens...")
    save_tokens_to_env(access_token, refresh_token)
    save_tokens_to_cache_file(access_token, refresh_token)
    
    print(f"\n🎉 ¡Proceso completado exitosamente!")
    print(f"Los tokens han sido guardados en el archivo .env")
    print(f"")
    print(f"📝 Próximos pasos:")
    print(f"1. Reinicia tu aplicación para que cargue los nuevos tokens")
    print(f"2. Verifica el estado en /config/dropbox/status")
    print(f"3. El sistema renovará automáticamente cada 45 minutos")
    
    print(f"\n🔒 Información de tokens:")
    print(f"Access Token: {access_token[:20]}...")
    print(f"Refresh Token: {refresh_token[:20]}...")

if __name__ == "__main__":
    main()
