#!/bin/bash

# Script de Verificación de Despliegue
# Verifica que todo esté funcionando correctamente

echo "🔍 Verificando estado del despliegue..."

# Verificar servicios
echo "📊 Estado de servicios:"
echo "========================"

# Verificar aplicación Flask
if systemctl is-active --quiet mydropboxapp; then
    echo "✅ mydropboxapp: ACTIVO"
else
    echo "❌ mydropboxapp: INACTIVO"
fi

# Verificar nginx
if systemctl is-active --quiet nginx; then
    echo "✅ nginx: ACTIVO"
else
    echo "❌ nginx: INACTIVO"
fi

# Verificar archivos importantes
echo ""
echo "📁 Verificando archivos importantes:"
echo "===================================="

PROJECT_PATH="/ruta/a/tu/proyecto/actual"

if [ -f "$PROJECT_PATH/run.py" ]; then
    echo "✅ run.py: PRESENTE"
else
    echo "❌ run.py: FALTANTE"
fi

if [ -f "$PROJECT_PATH/requirements.txt" ]; then
    echo "✅ requirements.txt: PRESENTE"
else
    echo "❌ requirements.txt: FALTANTE"
fi

if [ -d "$PROJECT_PATH/venv" ]; then
    echo "✅ Entorno virtual: PRESENTE"
else
    echo "❌ Entorno virtual: FALTANTE"
fi

if [ -f "$PROJECT_PATH/instance/mydropboxapp.db" ]; then
    echo "✅ Base de datos: PRESENTE"
else
    echo "❌ Base de datos: FALTANTE"
fi

# Verificar puertos
echo ""
echo "🌐 Verificando puertos:"
echo "======================"

if netstat -tuln | grep -q ":80 "; then
    echo "✅ Puerto 80: ABIERTO"
else
    echo "❌ Puerto 80: CERRADO"
fi

if netstat -tuln | grep -q ":443 "; then
    echo "✅ Puerto 443: ABIERTO"
else
    echo "❌ Puerto 443: CERRADO"
fi

# Verificar logs recientes
echo ""
echo "📋 Últimos logs de la aplicación:"
echo "================================="
journalctl -u mydropboxapp --since "10 minutes ago" --no-pager | tail -10

echo ""
echo "🎯 Verificación completada!" 