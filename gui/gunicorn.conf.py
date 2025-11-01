import os, multiprocessing
PORT = os.getenv("PORT", "5003")
bind = os.getenv("GUNICORN_BIND", f"0.0.0.0:{PORT}")
workers = int(os.getenv("WORKERS", os.getenv("WEB_CONCURRENCY", max(2, multiprocessing.cpu_count() // 2))))
threads = int(os.getenv("THREADS", 4))
timeout = int(os.getenv("GUNICORN_TIMEOUT", 60))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 30))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 30))
worker_class = os.getenv("WORKER_CLASS", "gthread")
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")
preload_app = os.getenv("GUNICORN_PRELOAD", "false").lower() == "true"










# bind = "127.0.0.1:5003"
# workers = 2
# threads = 4
# timeout = 0
# graceful_timeout = 30
# keepalive = 30
# worker_class = "gthread"
# accesslog = "-"
# errorlog = "-"
# loglevel = "info"



