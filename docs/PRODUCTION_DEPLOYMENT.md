# Production Deployment Guide

This project can run in production on both Linux and Windows without Nginx.

## 1. Prerequisites
- Python virtual environment ready (`.venv`)
- Redis available and reachable
- Database configured in `.env`
- `DJANGO_ENV=production`
- `DJANGO_DEBUG=False`

## 2. Install dependencies
```bash
pip install -r requirements.txt
```

## 3. Configure environment
Use `.env.example` as baseline and ensure these are set:
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `SERVE_STATIC_WITH_DJANGO=True`
- `REDIS_URL` (or split Redis variables)

Optional production knobs:
- `PRODUCTION_WEB_SERVER=auto`
- `PRODUCTION_WEB_BIND_HOST=0.0.0.0`
- `PRODUCTION_WEB_BIND_PORT=8000`
- `PRODUCTION_WEB_WORKERS=4`
- `PRODUCTION_WEB_THREADS=2`
- `PRODUCTION_WAITRESS_THREADS=8`
- `PRODUCTION_CELERY_WORKER_CONCURRENCY=4`
- `PRODUCTION_CELERY_LOGLEVEL=INFO`

## 4. Start production stack
```bash
python scripts/production_runner.py
```

This command launches:
- Web server (`gunicorn` on Linux, `waitress` on Windows)
- `celery worker`
- `celery beat`
- It forces `DJANGO_ENV=production` and `DJANGO_DEBUG=False`.

If one process exits, the runner stops the others to avoid split-brain state.

## 5. Linux service mode
1. Update file paths in `deploy/systemd/itsm-all.service`.
2. Install service:
```bash
sudo cp deploy/systemd/itsm-all.service /etc/systemd/system/itsm-all.service
sudo systemctl daemon-reload
sudo systemctl enable --now itsm-all
```
3. Check logs:
```bash
journalctl -u itsm-all -f
```

## 6. Windows service mode
Run as Administrator in PowerShell:
```powershell
.\deploy\windows\install-startup-task.ps1
```

The task runs `deploy/windows/start-itsm-prod.ps1` at startup under `SYSTEM`.

Remove startup task:
```powershell
.\deploy\windows\uninstall-startup-task.ps1
```

## 7. Notes
- In production, do not use `python manage.py runserver`.
- Keep only one `celery beat` instance to avoid duplicate schedules.
- WhiteNoise serves static files directly from Django for no-Nginx deployments.
