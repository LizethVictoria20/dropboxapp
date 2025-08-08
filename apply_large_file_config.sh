#!/bin/bash

# Script para aplicar configuración de archivos grandes
# Ejecutar como root o con sudo

echo "🔧 Aplicando configuración para archivos grandes..."

# 1. Verificar si nginx está instalado
if ! command -v nginx &> /dev/null; then
    echo "❌ nginx no está instalado"
    exit 1
fi

# 2. Crear backup de la configuración actual
echo "📋 Creando backup de la configuración actual..."
sudo cp /etc/nginx/sites-available/micaso.inmigracionokabogados.com /etc/nginx/sites-available/micaso.inmigracionokabogados.com.backup.$(date +%Y%m%d_%H%M%S)

# 3. Aplicar nueva configuración de nginx
echo "🔧 Aplicando nueva configuración de nginx..."
sudo tee /etc/nginx/sites-available/micaso.inmigracionokabogados.com > /dev/null << 'EOF'
server {
    server_name micaso.inmigracionokabogados.com;
    
    # Configuración para archivos grandes
    client_max_body_size 1G;
    client_body_timeout 300s;
    client_header_timeout 300s;
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
    send_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:8000;
        include proxy_params;
        
        # Configuración adicional para archivos grandes
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_max_temp_file_size 0;
    }

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/micaso.inmigracionokabogados.com/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/micaso.inmigracionokabogados.com/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot
}

server {
    if ($host = micaso.inmigracionokabogados.com) {
        return 301 https://$host$request_uri;
    } # managed by Certbot

    listen 80;
    server_name micaso.inmigracionokabogados.com;
    return 404; # managed by Certbot
}
EOF

# 4. Verificar configuración de nginx
echo "🔍 Verificando configuración de nginx..."
if sudo nginx -t; then
    echo "✅ Configuración de nginx válida"
else
    echo "❌ Error en la configuración de nginx"
    exit 1
fi

# 5. Recargar nginx
echo "🔄 Recargando nginx..."
sudo systemctl reload nginx

# 6. Verificar que nginx esté funcionando
if sudo systemctl is-active --quiet nginx; then
    echo "✅ nginx está funcionando correctamente"
else
    echo "❌ Error al recargar nginx"
    exit 1
fi

# 7. Mostrar configuración aplicada
echo ""
echo "📊 Configuración aplicada:"
echo "   - Tamaño máximo de archivo: 1GB"
echo "   - Timeout de conexión: 300s"
echo "   - Buffering deshabilitado para archivos grandes"
echo ""
echo "🎯 Para aplicar los cambios en la aplicación Flask:"
echo "   1. Reinicia el servicio de Gunicorn:"
echo "      sudo systemctl restart gunicorn"
echo "   2. O si usas supervisor:"
echo "      sudo supervisorctl restart mydropboxapp"
echo ""
echo "✅ Configuración completada exitosamente!" 