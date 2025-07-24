# Configuración de Gunicorn para producción
import multiprocessing

# Servidor
bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = "/var/log/mydropboxapp/access.log"
errorlog = "/var/log/mydropboxapp/error.log"
loglevel = "info"
access_log_format = '%h %l %u %t "%r" %s %b "%{Referer}i" "%{User-Agent}i"'

# Proceso
pidfile = "/var/run/mydropboxapp/mydropboxapp.pid"
user = "www-data"
group = "www-data"
tmp_upload_dir = None

# Seguridad
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Preload
preload_app = True 