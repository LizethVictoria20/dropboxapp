#!/bin/bash

# Script para Eliminar Proyecto Anterior de Forma Segura
# SOLO EJECUTAR DESPUÉS de verificar que el nuevo proyecto funciona correctamente

# Configuración (ajustar según tu configuración)
BACKUP_BASE_PATH="/ruta/backup"
PROJECT_NAME="mydropboxapp"

echo "🗑️ Script de Eliminación Segura del Proyecto Anterior"
echo "======================================================"
echo ""
echo "⚠️  ADVERTENCIA: Este script eliminará el proyecto anterior"
echo "   Asegúrate de que el nuevo proyecto funciona correctamente"
echo ""

# Verificar que el nuevo proyecto está funcionando
echo "🔍 Verificando estado del nuevo proyecto..."
if systemctl is-active --quiet mydropboxapp; then
    echo "✅ Nuevo proyecto: ACTIVO"
else
    echo "❌ Nuevo proyecto: INACTIVO"
    echo "   NO elimines el proyecto anterior hasta que el nuevo funcione"
    exit 1
fi

# Mostrar respaldos disponibles
echo ""
echo "📁 Respaldo disponible:"
echo "======================="
if [ -d "$BACKUP_BASE_PATH" ]; then
    ls -la "$BACKUP_BASE_PATH" | grep "$PROJECT_NAME"
else
    echo "❌ No se encontró directorio de respaldo"
    exit 1
fi

# Confirmación del usuario
echo ""
echo "🤔 ¿Estás seguro de que quieres eliminar el proyecto anterior?"
echo "   Esto liberará espacio en disco pero NO podrás recuperarlo fácilmente"
echo ""
read -p "Escribe 'ELIMINAR' para confirmar: " confirmacion

if [ "$confirmacion" != "ELIMINAR" ]; then
    echo "❌ Eliminación cancelada"
    exit 0
fi

# Crear respaldo adicional antes de eliminar
echo ""
echo "📦 Creando respaldo adicional..."
FECHA_ELIMINACION=$(date +%Y%m%d_%H%M%S)
RESPALDO_FINAL="$BACKUP_BASE_PATH/${PROJECT_NAME}_eliminado_$FECHA_ELIMINACION"

# Buscar el respaldo más reciente
RESPALDO_RECIENTE=$(ls -t "$BACKUP_BASE_PATH" | grep "$PROJECT_NAME" | head -1)

if [ -n "$RESPALDO_RECIENTE" ]; then
    cp -r "$BACKUP_BASE_PATH/$RESPALDO_RECIENTE" "$RESPALDO_FINAL"
    echo "✅ Respaldo adicional creado en: $RESPALDO_FINAL"
else
    echo "❌ No se encontró respaldo para copiar"
    exit 1
fi

# Eliminar respaldos antiguos (mantener solo los 3 más recientes)
echo ""
echo "🧹 Limpiando respaldos antiguos..."
RESPALDOS_ANTIGUOS=$(ls -t "$BACKUP_BASE_PATH" | grep "$PROJECT_NAME" | tail -n +4)

if [ -n "$RESPALDOS_ANTIGUOS" ]; then
    echo "Eliminando respaldos antiguos:"
    echo "$RESPALDOS_ANTIGUOS" | while read respaldo; do
        echo "   - $respaldo"
        rm -rf "$BACKUP_BASE_PATH/$respaldo"
    done
    echo "✅ Limpieza completada"
else
    echo "✅ No hay respaldos antiguos para eliminar"
fi

# Mostrar espacio liberado
echo ""
echo "💾 Espacio en disco:"
echo "==================="
df -h "$BACKUP_BASE_PATH"

echo ""
echo "✅ Proceso completado exitosamente!"
echo "📁 Respaldo final disponible en: $RESPALDO_FINAL"
echo "🎯 El proyecto anterior ha sido eliminado de forma segura" 