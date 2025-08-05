#!/usr/bin/env python3
"""
Script para desplegar el sistema de renovación automática al servidor
"""
import os
import subprocess
from pathlib import Path

def check_git_status():
    """Verifica el estado de git"""
    print("🔍 Verificando estado de Git...")
    
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

def create_deployment_script():
    """Crea un script de despliegue para el servidor"""
    print("📝 Creando script de despliegue...")
    
    deploy_script = '''#!/bin/bash
# Script de despliegue para el servidor
# Ejecutar en el servidor

echo "🚀 Desplegando sistema de renovación automática..."

# 1. Actualizar código desde git
echo "📥 Actualizando código..."
git pull origin main

# 2. Instalar dependencias si es necesario
echo "📦 Instalando dependencias..."
pip install -r requirements.txt

# 3. Verificar variables de entorno
echo "🔧 Verificando configuración..."
if [ ! -f .env ]; then
    echo "❌ Archivo .env no encontrado"
    echo "📝 Crea el archivo .env con las siguientes variables:"
    echo "SECRET_KEY=tu_secret_key"
    echo "DROPBOX_APP_KEY=abu5m0gdtp70bcw"
    echo "DROPBOX_APP_SECRET=6l3nsnj2jf99kai"
    echo "DROPBOX_ACCESS_TOKEN=tu_access_token"
    echo "DROPBOX_REFRESH_TOKEN=tu_refresh_token"
    exit 1
fi

# 4. Verificar que las variables están configuradas
echo "✅ Verificando variables de entorno..."
source .env

if [ -z "$DROPBOX_ACCESS_TOKEN" ]; then
    echo "❌ DROPBOX_ACCESS_TOKEN no configurado"
    exit 1
fi

if [ -z "$DROPBOX_APP_KEY" ]; then
    echo "❌ DROPBOX_APP_KEY no configurado"
    exit 1
fi

if [ -z "$DROPBOX_APP_SECRET" ]; then
    echo "❌ DROPBOX_APP_SECRET no configurado"
    exit 1
fi

echo "✅ Variables de entorno configuradas correctamente"

# 5. Reiniciar la aplicación
echo "🔄 Reiniciando aplicación..."
if command -v systemctl &> /dev/null; then
    # Si usa systemd
    sudo systemctl restart mydropboxapp
elif command -v supervisorctl &> /dev/null; then
    # Si usa supervisor
    sudo supervisorctl restart mydropboxapp
else
    echo "⚠️  No se detectó systemd ni supervisor"
    echo "🔄 Reinicia manualmente tu aplicación"
fi

# 6. Verificar que la aplicación está funcionando
echo "🔍 Verificando estado de la aplicación..."
sleep 5

if curl -f http://localhost:5000/config/dropbox/status &> /dev/null; then
    echo "✅ Aplicación funcionando correctamente"
else
    echo "❌ Error verificando la aplicación"
    echo "🔧 Revisa los logs de la aplicación"
fi

echo "🎉 ¡Despliegue completado!"
echo "💡 Visita /config/dropbox/status para ver el estado"
'''
    
    with open('deploy_server.sh', 'w') as f:
        f.write(deploy_script)
    
    # Hacer el script ejecutable
    os.chmod('deploy_server.sh', 0o755)
    
    print("✅ Script de despliegue creado: deploy_server.sh")

def create_env_template():
    """Crea una plantilla del archivo .env para el servidor"""
    print("📝 Creando plantilla de .env...")
    
    env_template = '''# Configuración de la aplicación
SECRET_KEY=35c9c274bfe5f6c4d4381fd22b05a47b6d54cabcde2156ef

# Configuración de Dropbox - OAuth 2
DROPBOX_APP_KEY=abu5m0gdtp70bcw
DROPBOX_APP_SECRET=6l3nsnj2jf99kai

# Token de acceso actual (se renovará automáticamente)
DROPBOX_ACCESS_TOKEN=sl.u.AF4im7fW76-NZwQ4CAye40IdVLnb6rnge3b5ZsRqf7JZZww0nhJsthqQME9f6o3rn4M3CHdcj5iyRbWmx2m3KmYMRN4dYNc01gY_gBPLMqWBf5oqkiM77HAQwV4xT8nCU-Yhyadr8swl2OARTA46OF-j06cG5SXmkTzNFeOLerA1mKCtyrSwl3NLK-qT4hRRXJV4JjmCtJ3WRvJ4E8Vf9mvN5EFxqp78WRbEKz46zPzZCeYy8Wd7MYAWtGWz64aug1uuv9FWyt4J_HV7gBQjz4Lhczdouvg4d-ThnR-o0Kz36p3VqRD8fV_xgmH04EK-LnfJhNd3KIKuXXvZmAU13xrlYUCs0epY6rro1vuJ1tmJiu3jI7t-dKRMm1nH5Pmxwc34fDVRBGUKgsnJtHFqQ1C7UXNlzT4g_IzPr91Huy2IZFvoNtMXP_D1ajxYs38glLE43YRmZcudsv4lxKzyVU573CfaOhHCw2rMKQV4ojdn6NxXi2euY4-pfOgeXY7qUTTDIV7UyixZYr-pub79XJK73HcqnyLKOkUZGu7AsjcUHsosb5YI74G-HokdvA2jWAFXizuXiPA8BY2CpwhM7mbbbIx5pm2iG8gzlabAs-61izH_93mPHaD3N1jn1ZNmAbCjOoz6VabzpziHmete1kqKNG6W9QAeos2oWwq_aGHsV_N4n36dD8NNtpdff9_k7s6KxwoRJgDO4aQB7IFmXfKQV9Hzx6ADIyG8cboouEtaVaCl1Lm6WqPuRrNDWE_NpCsr9hqAksrZ3fpey2ThGEf4DexnFvRfltFRuEHRIbma6JLEmel_PEeOFFdJgxLaYQ2YKrKIaXpicXlvz6alj-dLDuQhdlLYVAGVpoferG5UMJA3nqAAt2vn7KJX-77VrenUHn0E_O7HdG3cy28gwnx0XlB4VUktQPdeJkA1glE-bluW91AChs4rCtU5zKxClnxLfsWXPA-ToDTBaO58-GYFWwFSapoCZnXQ3biOjdzVgoYeb3-gOkUjkbt_jWwMSevS2coRmOK35Pw7qsS98R775-IrJFYfni__gRQpLYhGpyrTfzGJKYQmvULxmYIMsDGCa6FAJZqvQ2s19mcKoQKjhwRftQZUtkNuzjtjVkWy73AtvxBR0KuoXPGstN5TPqbi41dExFKia2AxjRapirgUCgludl1DXfpWVNXlb8A_Zxf2hWvz4GvvDWz-uIBI-KeqoIT3TBF8zypZcBBCsC-XezRezxjJWtl1kK3PMpNMo4L3TjFYNjkQuJgfhd-iKX-BBsnnh_COMBXYBx4oYd9DpwzEDYRGRuy9R3oT9vNHvF-edJ_ZnBSgm1l9CzNTYcRbHQFzC4uB9cKlsG_C96cweP-BnYuMW5NAV0Tu9-mTP6xJBLb4nk_Mw8LnHnbrGw0c9kqWRJY66CVz-NsJ3Dk8YQ0agI7Oohbjq3rlurRYtA

# Token de renovación (para renovación automática)
DROPBOX_REFRESH_TOKEN=tu_refresh_token_aqui

# Configuración de base de datos
DATABASE_URL=sqlite:///app.db

# Configuración de logging
LOG_LEVEL=INFO
'''
    
    with open('.env.template', 'w') as f:
        f.write(env_template)
    
    print("✅ Plantilla de .env creada: .env.template")

def create_server_instructions():
    """Crea instrucciones para el servidor"""
    print("📝 Creando instrucciones para el servidor...")
    
    instructions = '''# 🚀 Instrucciones de Despliegue en el Servidor

## 📋 Pasos para Desplegar el Sistema de Renovación Automática

### 1. Preparar el Servidor

```bash
# Conectar al servidor
ssh usuario@tu-servidor.com

# Navegar al directorio de la aplicación
cd /ruta/a/tu/aplicacion
```

### 2. Actualizar el Código

```bash
# Hacer pull de los cambios
git pull origin main

# Verificar que los archivos nuevos están presentes
ls -la app/dropbox_token_manager.py
ls -la app/dropbox_utils.py
```

### 3. Configurar Variables de Entorno

```bash
# Copiar la plantilla
cp .env.template .env

# Editar el archivo .env con tus credenciales
nano .env
```

**Variables necesarias en .env:**
- `DROPBOX_APP_KEY=abu5m0gdtp70bcw`
- `DROPBOX_APP_SECRET=6l3nsnj2jf99kai`
- `DROPBOX_ACCESS_TOKEN=tu_token_actual`
- `DROPBOX_REFRESH_TOKEN=tu_refresh_token` (opcional)

### 4. Instalar Dependencias

```bash
# Instalar dependencias si es necesario
pip install -r requirements.txt
```

### 5. Reiniciar la Aplicación

**Si usas systemd:**
```bash
sudo systemctl restart mydropboxapp
sudo systemctl status mydropboxapp
```

**Si usas supervisor:**
```bash
sudo supervisorctl restart mydropboxapp
sudo supervisorctl status mydropboxapp
```

**Si usas PM2:**
```bash
pm2 restart mydropboxapp
pm2 status
```

### 6. Verificar el Funcionamiento

```bash
# Verificar que la aplicación responde
curl http://localhost:5000/config/dropbox/status

# Verificar logs
sudo journalctl -u mydropboxapp -f
```

### 7. Monitoreo

- **Estado en tiempo real**: Visita `/config/dropbox/status`
- **Logs de renovación**: Revisa los logs de la aplicación
- **Renovación automática**: Cada 45 minutos automáticamente

## 🔧 Solución de Problemas

### Error: "No hay token de acceso disponible"
- Verifica que `DROPBOX_ACCESS_TOKEN` esté configurado en `.env`
- Asegúrate de que el token sea válido

### Error: "DROPBOX_APP_KEY no configurado"
- Verifica que `DROPBOX_APP_KEY` y `DROPBOX_APP_SECRET` estén en `.env`

### La aplicación no se reinicia
- Verifica los permisos del usuario
- Revisa los logs del sistema: `sudo journalctl -u mydropboxapp`

### Renovación automática no funciona
- Verifica que `DROPBOX_REFRESH_TOKEN` esté configurado
- Revisa los logs de la aplicación para errores

## 📊 Verificación Final

1. **Visita** `/config/dropbox/status` en tu navegador
2. **Verifica** que muestra "Conectado" y no errores
3. **Confirma** que "Auto refresh habilitado" aparece como "True"
4. **Prueba** una operación de Dropbox desde la aplicación

## 🎉 ¡Listo!

Tu sistema de renovación automática estará funcionando en el servidor.
'''
    
    with open('INSTRUCCIONES_SERVIDOR.md', 'w') as f:
        f.write(instructions)
    
    print("✅ Instrucciones creadas: INSTRUCCIONES_SERVIDOR.md")

def main():
    """Función principal"""
    print("🚀 Preparando despliegue al servidor...")
    
    # Verificar git
    if not check_git_status():
        print("❌ Hay cambios sin commitear. Haz commit antes de desplegar.")
        return
    
    # Crear archivos de despliegue
    create_deployment_script()
    create_env_template()
    create_server_instructions()
    
    print("\n✅ Archivos de despliegue creados:")
    print("  - deploy_server.sh (script de despliegue)")
    print("  - .env.template (plantilla de variables)")
    print("  - INSTRUCCIONES_SERVIDOR.md (instrucciones detalladas)")
    
    print("\n📋 Próximos pasos:")
    print("1. Sube los cambios a git: git push origin main")
    print("2. Copia los archivos al servidor")
    print("3. Ejecuta el script de despliegue en el servidor")
    print("4. Verifica que todo funciona en /config/dropbox/status")

if __name__ == "__main__":
    main() 