# MyDropboxApp

Una aplicación web para gestionar archivos en Dropbox con diferentes roles de usuario.

## Características

- Gestión de archivos y carpetas en Dropbox
- Múltiples roles de usuario (admin, cliente, lector)
- Sistema de permisos granular para lectores
- Interfaz web moderna con Tailwind CSS

## Roles de Usuario

### Admin

- Acceso completo a todas las funcionalidades
- Puede gestionar usuarios y carpetas
- Puede ver y modificar archivos de todos los usuarios

### Cliente

- Acceso a sus propias carpetas y archivos
- Puede subir, mover, renombrar y eliminar sus archivos
- Puede gestionar beneficiarios

### Lector

- Acceso de solo lectura por defecto
- Puede ver todas las carpetas y archivos de todos los usuarios
- **Permisos adicionales configurables:**
  - **Renombrar archivos**: Permite cambiar el nombre de archivos
  - **Mover archivos**: Permite mover archivos entre carpetas
  - **Eliminar archivos**: Permite eliminar archivos
  - **Agregar beneficiarios**: Permite gestionar beneficiarios

## Configuración de Permisos de Lector

Los permisos adicionales para lectores se configuran desde el panel de administración:

1. Ir a "Gestionar Usuarios"
2. Seleccionar un usuario con rol "lector"
3. En la sección "Permisos Adicionales para Lector", marcar los permisos deseados:
   - ✅ Renombrar
   - ✅ Mover
   - ✅ Eliminar
   - ✅ Agregar beneficiarios

**Nota importante**: Al marcar cualquiera de estos permisos, el rol "Lector" se selecciona automáticamente para garantizar la coherencia del sistema.

### Comportamiento de la Interfaz

- **Sin permisos adicionales**: El lector ve un mensaje azul indicando "Modo Lector - Acceso de Solo Lectura"
- **Con permisos adicionales**: El lector ve un mensaje verde indicando "Modo Lector - Acceso con Permisos de Modificación"
- **Botones de acción**: Solo aparecen cuando el lector tiene los permisos correspondientes

### Verificación de Seguridad

Todas las acciones están protegidas tanto en el frontend como en el backend:

- **Frontend**: Los botones solo se muestran si el usuario tiene permisos
- **Backend**: Cada ruta verifica los permisos antes de ejecutar la acción
- **Mensajes de error**: Se muestran mensajes claros cuando se deniega el acceso

## Instalación

1. Clonar el repositorio
2. Instalar dependencias: `pip install -r requirements.txt`
3. Configurar variables de entorno (DROPBOX_API_KEY, etc.)
4. Ejecutar migraciones: `flask db upgrade`
5. Iniciar la aplicación: `python run.py`

## Uso

1. Crear un usuario administrador
2. Configurar permisos de lectores según sea necesario
3. Los lectores podrán acceder a las carpetas de usuarios con los permisos configurados

## Notas Técnicas

- Los permisos se almacenan en formato JSON en el campo `lector_extra_permissions`
- Las verificaciones de permisos se realizan en el modelo `User` con métodos específicos
- Todas las rutas de modificación incluyen verificaciones de seguridad
