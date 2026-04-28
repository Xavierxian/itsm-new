import atexit
import os
import subprocess
import sys
import time


_AUTOSTART_PROCESSES = []
_ATEXIT_REGISTERED = False


def _env_bool(value, default):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _redis_configured():
    redis_url = str(os.getenv("REDIS_URL", "") or "").strip()
    redis_host = str(os.getenv("REDIS_HOST", "") or "").strip()
    return bool(redis_url or redis_host)


def _stop_autostart_processes():
    global _AUTOSTART_PROCESSES
    if not _AUTOSTART_PROCESSES:
        return

    for process in list(_AUTOSTART_PROCESSES):
        if process.poll() is not None:
            continue
        process.terminate()

    for process in list(_AUTOSTART_PROCESSES):
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    _AUTOSTART_PROCESSES = []


def maybe_start_runserver_scheduler(argv):
    """
    Auto-start local Celery worker and beat processes when running Django dev server.
    """
    global _ATEXIT_REGISTERED, _AUTOSTART_PROCESSES

    is_runserver = len(argv) > 1 and argv[1] == "runserver"
    if not is_runserver:
        return

    # runserver's autoreload child process should not re-spawn another scheduler.
    if os.environ.get("RUN_MAIN") == "true":
        return

    if not _env_bool(os.getenv("AUTO_START_CELERY_ON_RUNSERVER"), True):
        return

    if str(os.getenv("DJANGO_ENV", "development") or "").strip().lower() in {"prod", "production"}:
        return

    if not _redis_configured():
        print("[autostart] REDIS_URL/REDIS_HOST not configured, skip Celery autostart.")
        return

    if any(process.poll() is None for process in _AUTOSTART_PROCESSES):
        return

    commands = [
        (
            "worker",
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "config",
                "worker",
                "--pool=solo",
                "--loglevel=INFO",
                "--hostname=itsm_autostart_worker@%h",
            ],
        ),
        (
            "beat",
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "config",
                "beat",
                "--loglevel=INFO",
            ],
        ),
    ]
    env = os.environ.copy()
    env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    try:
        _AUTOSTART_PROCESSES = []
        started = []
        for role, command in commands:
            process = subprocess.Popen(command, env=env)
            started.append((role, process))
            _AUTOSTART_PROCESSES.append(process)
            time.sleep(0.25)
            if process.poll() is not None:
                _stop_autostart_processes()
                print(
                    f"[autostart] Failed to start Celery {role}, "
                    f"exit_code={process.returncode}. Please run manually."
                )
                return

        if not _ATEXIT_REGISTERED:
            atexit.register(_stop_autostart_processes)
            _ATEXIT_REGISTERED = True
        pids_text = ", ".join(f"{role}={process.pid}" for role, process in started)
        print(f"[autostart] Celery started: {pids_text}.")
    except OSError as exc:
        _stop_autostart_processes()
        print(f"[autostart] Failed to start Celery processes: {exc}")
