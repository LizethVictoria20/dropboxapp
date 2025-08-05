#!/usr/bin/env python3
"""
Script para verificar que todos los archivos necesarios estén presentes
"""
import os
from pathlib import Path

def verificar_archivos():
    """Verifica que todos los archivos necesarios estén presentes"""
    print("🔍 Verificando archivos necesarios...")
    
    archivos_requeridos = [
        # Archivos principales del sistema de renovación
        'app/dropbox_token_manager.py',
        'app/dropbox_utils.py',
        'app/routes/main.py',
        'app/templates/config_status.html',
        'config.py',
        
        # Archivos de despliegue
        'deploy_server.sh',
        '.env.template',
        'INSTRUCCIONES_SERVIDOR.md',
        'README_TOKEN_RENEWAL.md',
        
        # Archivos de configuración
        'requirements.txt',
        'run.py',
        'wsgi.py'
    ]
    
    archivos_faltantes = []
    archivos_presentes = []
    
    for archivo in archivos_requeridos:
        if Path(archivo).exists():
            archivos_presentes.append(archivo)
            print(f"✅ {archivo}")
        else:
            archivos_faltantes.append(archivo)
            print(f"❌ {archivo}")
    
    print(f"\n📊 Resumen:")
    print(f"  - Archivos presentes: {len(archivos_presentes)}")
    print(f"  - Archivos faltantes: {len(archivos_faltantes)}")
    
    if archivos_faltantes:
        print(f"\n❌ Archivos faltantes:")
        for archivo in archivos_faltantes:
            print(f"  - {archivo}")
        return False
    else:
        print(f"\n✅ Todos los archivos están presentes")
        return True

def verificar_contenido_archivos():
    """Verifica el contenido de archivos críticos"""
    print("\n🔍 Verificando contenido de archivos críticos...")
    
    # Verificar dropbox_token_manager.py
    token_manager_path = 'app/dropbox_token_manager.py'
    if Path(token_manager_path).exists():
        with open(token_manager_path, 'r') as f:
            contenido = f.read()
            if 'class DropboxTokenManager:' in contenido:
                print("✅ app/dropbox_token_manager.py - Contenido correcto")
            else:
                print("❌ app/dropbox_token_manager.py - Contenido incorrecto")
                return False
    else:
        print("❌ app/dropbox_token_manager.py - No encontrado")
        return False
    
    # Verificar dropbox_utils.py
    utils_path = 'app/dropbox_utils.py'
    if Path(utils_path).exists():
        with open(utils_path, 'r') as f:
            contenido = f.read()
            if 'get_dbx()' in contenido and 'get_valid_dropbox_token()' in contenido:
                print("✅ app/dropbox_utils.py - Contenido correcto")
            else:
                print("❌ app/dropbox_utils.py - Contenido incorrecto")
                return False
    else:
        print("❌ app/dropbox_utils.py - No encontrado")
        return False
    
    # Verificar config.py
    config_path = 'config.py'
    if Path(config_path).exists():
        with open(config_path, 'r') as f:
            contenido = f.read()
            if 'DROPBOX_REFRESH_TOKEN' in contenido:
                print("✅ config.py - Contenido correcto")
            else:
                print("❌ config.py - Contenido incorrecto")
                return False
    else:
        print("❌ config.py - No encontrado")
        return False
    
    return True

def verificar_git():
    """Verifica el estado de git"""
    print("\n🔍 Verificando estado de Git...")
    
    import subprocess
    
    try:
        # Verificar si hay cambios sin commitear
        result = subprocess.run(['git', 'status', '--porcelain'], 
                              capture_output=True, text=True)
        
        if result.stdout.strip():
            print("⚠️  Hay cambios sin commitear:")
            print(result.stdout)
            return False
        else:
            print("✅ No hay cambios pendientes")
            return True
            
    except Exception as e:
        print(f"❌ Error verificando git: {e}")
        return False

def main():
    """Función principal"""
    print("🚀 Verificando archivos para despliegue...")
    print("=" * 50)
    
    # Verificar archivos
    archivos_ok = verificar_archivos()
    
    # Verificar contenido
    contenido_ok = verificar_contenido_archivos()
    
    # Verificar git
    git_ok = verificar_git()
    
    print("\n" + "=" * 50)
    
    if archivos_ok and contenido_ok and git_ok:
        print("✅ ¡Todo listo para despliegue!")
        print("\n📋 Próximos pasos:")
        print("1. Conecta al servidor")
        print("2. Ejecuta: git pull origin main")
        print("3. Configura el archivo .env")
        print("4. Reinicia la aplicación")
        print("5. Verifica en /config/dropbox/status")
    else:
        print("❌ Hay problemas que resolver antes del despliegue")
        
        if not archivos_ok:
            print("  - Faltan archivos necesarios")
        if not contenido_ok:
            print("  - Contenido de archivos incorrecto")
        if not git_ok:
            print("  - Hay cambios sin commitear")

if __name__ == "__main__":
    main() 