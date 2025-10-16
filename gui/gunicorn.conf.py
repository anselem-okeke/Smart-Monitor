bind = "127.0.0.1:5003"
workers = 2
threads = 4
timeout = 0
graceful_timeout = 30
keepalive = 30
worker_class = "gthread"
accesslog = "-"
errorlog = "-"
loglevel = "info"

# # gunicorn.py
# bind = "127.0.0.1:5003"
# workers = 2
# threads = 4
# # Option 1: no timeout for long-lived SSE
# timeout = 0
# graceful_timeout = 30
# keepalive = 30
# worker_class = "gthread"
# accesslog = "-"
# errorlog = "-"
# loglevel = "info"
