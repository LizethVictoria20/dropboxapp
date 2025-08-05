# 🚀 Instrucciones de Despliegue en el Servidor

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