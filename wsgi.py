"""Production entry point:  gunicorn wsgi:app   (or waitress-serve --call wsgi:create)"""
from pbf import create_app

app = create_app()
