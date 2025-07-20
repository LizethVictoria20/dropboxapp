# 🚀 Guía Rápida - Dashboard Estadístico

## ⚡ Inicio Rápido

### 1. **Ejecutar la Aplicación**

```bash
# Navegar al directorio del proyecto
cd /Users/lizethvictoriafranco/Projects/VPT/mydropboxapp

# Ejecutar el servidor Flask
python manage.py
```

### 2. **Acceder al Dashboard**

- **URL**: http://localhost:5000/dashboard/admin
- **Credenciales de Prueba**:
  - Email: `admin@example.com`
  - Contraseña: `123456`

### 3. **Crear Datos de Ejemplo** (Si es necesario)

```bash
python create_sample_dashboard_data.py
```

## 📊 Funcionalidades Principales

### **Selector de Período**

- **Hoy**: Datos por hora del día actual
- **Semana**: Datos por día de la semana actual
- **Mes**: Datos por semana del mes actual
- **Año**: Datos por mes del año actual

### **Métricas Dinámicas**

- ✅ Usuarios nuevos del período
- ✅ Clientes nuevos del período
- ✅ Archivos subidos del período
- ✅ Carpetas creadas del período

### **Gráficas Interactivas**

- 📈 **Líneas**: Tendencias de archivos y usuarios
- 🍩 **Circulares**: Distribución de tipos de archivo
- 📊 **Anuales**: Evolución histórica

### **Controles**

- 🔄 **Botón Actualizar**: Refresca datos en tiempo real
- 📱 **Responsive**: Se adapta a móvil y desktop
- 🖱️ **Hover**: Tooltips informativos en gráficas

## 🎯 Casos de Uso

### **Para Administradores**

1. **Monitoreo Diario**: Cambiar a "Hoy" para ver actividad del día
2. **Análisis Semanal**: Usar "Semana" para tendencias semanales
3. **Reportes Mensuales**: Seleccionar "Mes" para informes
4. **Planificación Anual**: Ver "Año" para análisis de largo plazo

### **Métricas Clave a Monitorear**

- 📈 **Crecimiento de usuarios**: Tendencia ascendente
- 📁 **Actividad de archivos**: Subidas constantes
- 🗂️ **Organización**: Creación de carpetas
- 📊 **Tipos de contenido**: Distribución balanceada

## 🔧 Resolución de Problemas

### **Si no ves datos en las gráficas**

```bash
# Ejecutar el script de datos de ejemplo
python create_sample_dashboard_data.py
```

### **Si hay errores de carga**

1. Verificar que el servidor esté ejecutándose
2. Revisar la consola del navegador (F12)
3. Verificar conexión a internet (para Chart.js CDN)

### **Si las gráficas no se actualizan**

1. Hacer clic en "Actualizar datos"
2. Cambiar el período y volver al original
3. Recargar la página (F5)

## 📱 Navegación Mobile

- **Menú responsive**: Se adapta automáticamente
- **Gráficas táctiles**: Zoom y desplazamiento
- **Controles optimizados**: Botones grandes para tocar

## 🎨 Personalización

### **Colores del Sistema**

- Primario: `#0076a8` (Azul corporativo)
- Secundario: `#00a8d4` (Azul claro)
- Superficie: `#F0F7FC` (Gris azulado)

### **Modificar Períodos**

Editar en `app/utils/dashboard_stats.py`:

```python
def calculate_period_dates(period):
    # Agregar nuevos períodos aquí
```

## 🚨 Notas Importantes

1. **Datos Reales**: El dashboard usa datos reales de la base de datos
2. **Rendimiento**: Las consultas están optimizadas para SQLite
3. **Seguridad**: Solo usuarios admin pueden acceder
4. **Tiempo Real**: Los datos se actualizan automáticamente

## 📞 Soporte

Si encuentras problemas:

1. Revisar logs en la terminal donde corre Flask
2. Verificar la consola del navegador
3. Comprobar que todos los archivos estén en su lugar
4. Verificar permisos de base de datos

---

## ✅ Lista de Verificación

- [ ] Servidor Flask ejecutándose
- [ ] Base de datos con datos
- [ ] Usuario admin creado
- [ ] Navegador con JavaScript habilitado
- [ ] Acceso a internet (para CDNs)

**¡Disfruta de tu nuevo dashboard estadístico! 📊✨**
