"""WSGI entrypoint for gunicorn / cloud platforms.

Run with: gunicorn -w 2 -b 0.0.0.0:$PORT wsgi:app

Reads config from the CONFIG_PATH env var, defaulting to config.yaml in
the working directory. Falls back to built-in defaults if neither exists,
so the dashboard still comes up on a fresh deploy without extra setup.
"""
import os
from pathlib import Path

from watchtower.config import load_config
from watchtower.web import create_app

config_path = os.environ.get("CONFIG_PATH", "config.yaml")
config = load_config(config_path if Path(config_path).exists() else None)

app = create_app(config)
