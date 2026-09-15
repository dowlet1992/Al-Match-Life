#!/bin/sh
set -eu

exec python3 -m gunicorn \
    --config gunicorn.conf.py \
    --bind "${GUNICORN_BIND:-127.0.0.1:8000}" \
    app:app
