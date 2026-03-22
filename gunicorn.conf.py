# Gunicorn configuration file to enforce ASGI (Uvicorn) workers and correct app targeting
import os

# Set worker class to Uvicorn for ASGI support (FastAPI)
worker_class = 'uvicorn.workers.UvicornWorker'

# Bind to the port provided by Render
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

# Target the correct FastAPI instance in the backend subfolder
wsgi_app = "backend.app:app"

# Resource management for Render free tier
workers = 1
timeout = 120
keepalive = 5
