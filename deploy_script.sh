#!/bin/bash

# Script de Despliegue Seguro para MyDropboxApp
# Este script reemplaza el proyecto actual sin afectar configuración del servidor

# Configuración
REMOTE_USER="tu_usuario"
REMOTE_HOST="tu_servidor.com"
REMOTE_PATH="/ruta/a/tu/proyecto/actual"
BACKUP_PATH="/ruta/backup/$(date +%Y%m%d_%H%M%S)"
NEW_PROJECT_PATH="/tmp/mydropboxapp_new"

echo "🚀 Iniciando despliegue seguro de MyDropboxApp..."

# Paso 1: Crear respaldo del proyecto actual
echo "📦 Creando respaldo del proyecto actual..."
ssh $REMOTE_USER@$REMOTE_HOST "mkdir -p $BACKUP_PATH && cp -r $REMOTE_PATH/* $BACKUP_PATH/"

if [ $? -eq 0 ]; then
    echo "✅ Respaldo creado exitosamente en: $BACKUP_PATH"
else
    echo "❌ Error al crear respaldo. Abortando despliegue."
    exit 1
fi

# Paso 2: Subir nuevo proyecto
echo "📤 Subiendo nuevo proyecto..."
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='node_modules' --exclude='instance' ./ $REMOTE_USER@$REMOTE_HOST:$NEW_PROJECT_PATH/

if [ $? -eq 0 ]; then
    echo "✅ Proyecto subido exitosamente"
else
    echo "❌ Error al subir proyecto. Abortando despliegue."
    exit 1
fi

# Paso 3: Preservar archivos de configuración importantes
echo "🔧 Preservando archivos de configuración..."
ssh $REMOTE_USER@$REMOTE_HOST "
    # Preservar configuración de base de datos
    if [ -f $REMOTE_PATH/instance/mydropboxapp.db ]; then
        cp $REMOTE_PATH/instance/mydropboxapp.db $NEW_PROJECT_PATH/instance/
        echo '✅ Base de datos preservada'
    fi
    
    # Preservar variables de entorno
    if [ -f $REMOTE_PATH/.env ]; then
        cp $REMOTE_PATH/.env $NEW_PROJECT_PATH/
        echo '✅ Variables de entorno preservadas'
    fi
    
    # Preservar logs si existen
    if [ -d $REMOTE_PATH/logs ]; then
        cp -r $REMOTE_PATH/logs $NEW_PROJECT_PATH/
        echo '✅ Logs preservados'
    fi
"

# Paso 4: Instalar dependencias
echo "📦 Instalando dependencias..."
ssh $REMOTE_USER@$REMOTE_HOST "
    cd $NEW_PROJECT_PATH
    pip install -r requirements.txt
    npm install
    npm run build
"

# Paso 5: Ejecutar migraciones
echo "🔄 Ejecutando migraciones..."
ssh $REMOTE_USER@$REMOTE_HOST "
    cd $NEW_PROJECT_PATH
    export FLASK_APP=run.py
    flask db upgrade
"

# Paso 6: Reemplazar proyecto actual
echo "🔄 Reemplazando proyecto actual..."
ssh $REMOTE_USER@$REMOTE_HOST "
    # Detener aplicación actual si está corriendo
    sudo systemctl stop mydropboxapp 2>/dev/null || true
    
    # Reemplazar proyecto
    rm -rf $REMOTE_PATH
    mv $NEW_PROJECT_PATH $REMOTE_PATH
    
    # Asegurar permisos correctos
    chown -R $REMOTE_USER:$REMOTE_USER $REMOTE_PATH
    chmod -R 755 $REMOTE_PATH
"

# Paso 7: Reiniciar servicios
echo "🔄 Reiniciando servicios..."
ssh $REMOTE_USER@$REMOTE_HOST "
    # Reiniciar aplicación
    sudo systemctl start mydropboxapp
    sudo systemctl enable mydropboxapp
    
    # Reiniciar nginx si es necesario
    sudo systemctl reload nginx
"

echo "✅ Despliegue completado exitosamente!"
echo "📁 Respaldo disponible en: $BACKUP_PATH"
echo "🌐 Aplicación disponible en tu dominio configurado" 