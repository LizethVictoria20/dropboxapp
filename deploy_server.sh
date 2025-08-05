#!/bin/bash
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
