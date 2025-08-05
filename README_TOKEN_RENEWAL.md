# Sistema de Renovación Automática de Tokens de Dropbox

## 📋 Descripción

Este sistema implementa una renovación automática de tokens de Dropbox para evitar que la plataforma se caiga cuando los tokens expiren. El sistema incluye:

- ✅ Renovación automática cada 45 minutos
- ✅ Renovación manual desde la interfaz web
- ✅ Almacenamiento seguro de tokens
- ✅ Manejo de errores robusto
- ✅ Interfaz de monitoreo en tiempo real

## 🚀 Instalación y Configuración

### 1. Variables de Entorno Requeridas

Agrega estas variables a tu archivo `.env`:

```bash
# Tokens de Dropbox (obligatorios)
DROPBOX_ACCESS_TOKEN=tu_access_token_aqui
DROPBOX_APP_KEY=tu_app_key_aqui
DROPBOX_APP_SECRET=tu_app_secret_aqui

# Para renovación automática (recomendado)
DROPBOX_REFRESH_TOKEN=tu_refresh_token_aqui
```

### 2. Obtener Refresh Token

Para habilitar la renovación automática, necesitas un refresh token:

```bash
# Ejecutar el script de generación
python generate_refresh_token.py
```

Este script te guiará para obtener un refresh token desde Dropbox.

### 3. Verificar Instalación

```bash
# Probar el sistema completo
python test_token_refresh.py
```

## 🔧 Funcionalidades

### Renovación Automática

- **Frecuencia**: Cada 45 minutos
- **Thread**: Ejecuta en background sin afectar la aplicación
- **Logs**: Registra todas las renovaciones en los logs
- **Fallback**: Si falla la renovación, usa el token actual

### Renovación Manual

- **Interfaz Web**: Botón en `/config/dropbox/status`
- **API**: Endpoint POST `/config/dropbox/refresh`
- **Logs**: Registra intentos de renovación manual

### Monitoreo

- **Estado en Tiempo Real**: `/config/dropbox/status`
- **Información de Tokens**: Última renovación, próxima renovación
- **Estado de Conexión**: Verificación automática de conectividad

## 📁 Archivos del Sistema

### Core
- `app/dropbox_token_manager.py` - Gestor principal de tokens
- `app/dropbox_utils.py` - Utilidades actualizadas para usar el gestor
- `config.py` - Configuración actualizada con nueva variable

### Scripts
- `generate_refresh_token.py` - Genera refresh token
- `test_token_refresh.py` - Pruebas del sistema

### Templates
- `app/templates/config_status.html` - Interfaz de monitoreo

## 🔄 Flujo de Renovación

1. **Inicialización**: Al arrancar la app, se crea el gestor de tokens
2. **Thread Background**: Se inicia un thread que renueva cada 45 minutos
3. **Verificación**: Antes de cada operación, verifica si necesita renovar
4. **Almacenamiento**: Guarda tokens actualizados en `.dropbox_tokens.json`
5. **Variables de Entorno**: Actualiza las variables automáticamente

## 🛠️ Uso

### Verificar Estado

```python
from app.dropbox_token_manager import get_token_manager

manager = get_token_manager()
status = manager.get_token_status()
print(f"Auto refresh habilitado: {status['refresh_token_configured']}")
```

### Renovar Manualmente

```python
from app.dropbox_token_manager import refresh_dropbox_token

success = refresh_dropbox_token()
if success:
    print("Token renovado exitosamente")
```

### Obtener Token Válido

```python
from app.dropbox_token_manager import get_valid_dropbox_token

token = get_valid_dropbox_token()
# Usar token para operaciones de Dropbox
```

## 🔍 Monitoreo y Debugging

### Logs

El sistema registra todas las operaciones:

```
INFO:app.dropbox_token_manager:Thread de renovación automática iniciado
INFO:app.dropbox_token_manager:Renovación automática de token...
INFO:app.dropbox_token_manager:Token de acceso renovado exitosamente
```

### Estado Web

Visita `/config/dropbox/status` para ver:

- Estado de todas las variables
- Información de conexión
- Estado de renovación automática
- Botón de renovación manual

### Archivo de Tokens

Los tokens se guardan en `.dropbox_tokens.json`:

```json
{
  "access_token": "nuevo_token_aqui",
  "refresh_token": "refresh_token_aqui",
  "last_refresh": "2024-01-15T10:30:00"
}
```

## ⚠️ Solución de Problemas

### Error: "No hay refresh token disponible"

1. Ejecuta `python generate_refresh_token.py`
2. Sigue las instrucciones para obtener refresh token
3. Agrega `DROPBOX_REFRESH_TOKEN` al archivo `.env`

### Error: "Error renovando token"

1. Verifica que `DROPBOX_APP_KEY` y `DROPBOX_APP_SECRET` estén configurados
2. Asegúrate de que el refresh token sea válido
3. Revisa los logs para más detalles

### Error: "Token de acceso de Dropbox inválido o expirado"

1. El sistema debería renovar automáticamente
2. Si persiste, usa el botón de renovación manual
3. Verifica la conectividad con Dropbox

## 🔒 Seguridad

- Los tokens se almacenan en archivo local (`.dropbox_tokens.json`)
- Las variables de entorno se actualizan automáticamente
- El thread de renovación es daemon (se cierra con la app)
- Todos los errores se manejan de forma segura

## 📈 Beneficios

- ✅ **Sin Interrupciones**: La plataforma no se cae por tokens expirados
- ✅ **Automático**: No requiere intervención manual
- ✅ **Monitoreable**: Interfaz web para verificar estado
- ✅ **Robusto**: Manejo de errores y fallbacks
- ✅ **Seguro**: Almacenamiento y actualización segura de tokens

## 🎯 Próximos Pasos

1. Configura las variables de entorno
2. Ejecuta `python generate_refresh_token.py` para obtener refresh token
3. Prueba el sistema con `python test_token_refresh.py`
4. Verifica el estado en `/config/dropbox/status`
5. ¡Disfruta de la renovación automática! 