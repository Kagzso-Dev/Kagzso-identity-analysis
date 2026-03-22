# This file proxies the FastAPI app and adds WSGI compatibility for standard Gunicorn workers
from a2wsgi import ASGIMiddleware
from backend.app import app as asgi_app

# The 'app' object here is now a standard WSGI app that Gunicorn understands natively
app = ASGIMiddleware(asgi_app)
