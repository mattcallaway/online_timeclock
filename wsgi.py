"""Gunicorn / production entrypoint. Run: gunicorn wsgi:app"""
import os
from dotenv import load_dotenv
load_dotenv()

from app import create_app

app = create_app("production")
