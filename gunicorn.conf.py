# Configuración de Gunicorn para archivos grandes
import multiprocessing

# Configuración básica
bind = "127.0.0.1:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000

# Configuración para archivos grandes
max_requests = 1000
max_requests_jitter = 50
timeout = 300  # 5 minutos
keepalive = 2
preload_app = True

# Configuración de logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Configuración de seguridad
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# Configuración para archivos grandes
worker_tmp_dir = "/dev/shm"  # Usar memoria compartida para archivos temporales 