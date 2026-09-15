# Al-Match-Life
AI platform for finding the right people for life, business and growth

## Local web application

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Start the local application through Gunicorn:

```bash
GUNICORN_BIND=127.0.0.1:5001 WEB_CONCURRENCY=2 GUNICORN_THREADS=2 ./scripts/run_web.sh
```

Open [http://127.0.0.1:5001](http://127.0.0.1:5001). The local command uses port
`5001` because macOS commonly reserves port `5000` for AirPlay and returns a
`403` response there.

The direct `python3 app.py` command is development-only. Production uses the
same launcher with environment-specific bind, concurrency, secrets, database,
proxy and provider configuration:

```bash
APP_ENV=production GUNICORN_BIND=127.0.0.1:8000 ./scripts/run_web.sh
```

`GUNICORN_BIND` defaults to `127.0.0.1:8000`.

Gunicorn intentionally uses one worker process while `STORAGE_BACKEND=json`;
threads remain enabled for local concurrency. Multiple worker processes are
enabled only with `STORAGE_BACKEND=postgres`, preventing cross-process writes
from corrupting development JSON stores.
