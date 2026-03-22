# Use Gunicorn with Uvicorn workers for production stability on Render
web: gunicorn -w 1 -k uvicorn.workers.UvicornWorker backend.app:app --bind 0.0.0.0:$PORT
