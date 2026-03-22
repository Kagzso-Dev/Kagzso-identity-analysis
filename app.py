# This file exists to proxy the FastAPI app from the backend subfolder
# This allows 'gunicorn app:app' to work from the project root
from backend.app import app

# This ensures that even if Gunicorn defaults to a sync worker, 
# it still has access to the FastAPI app object.
