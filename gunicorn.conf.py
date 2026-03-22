# gunicorn.conf.py — only used if gunicorn is invoked directly (not the primary path)
# Primary start: uvicorn (see render.yaml startCommand and Procfile)
import os

worker_class = 'uvicorn.workers.UvicornWorker'
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1
timeout = 120
keepalive = 5
# App is specified on the command line, not here
