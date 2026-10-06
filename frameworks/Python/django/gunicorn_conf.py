import multiprocessing
import os

_is_travis = os.environ.get('TRAVIS') == 'true'

workers = multiprocessing.cpu_count()
if _is_travis:
    workers = 2
if os.environ.get('RC_WORKERS'):
    workers = int(os.environ['RC_WORKERS'])

bind = "0.0.0.0:8080"
keepalive = 120
errorlog = '-'
pidfile = 'gunicorn.pid'
pythonpath = 'hello'
worker_class = 'gthread'
threads = int(os.environ.get('RC_THREADS') or 4)