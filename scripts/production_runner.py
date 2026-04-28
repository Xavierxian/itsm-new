from __future__ import annotations

import argparse
import importlib.util
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE_DIR / "runtime"
CELERY_RUNTIME_DIR = RUNTIME_DIR / "celery"
CELERY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

_SHUTDOWN_REQUESTED = False


@dataclass(frozen=True)
class ProcessSpec:
    name: str
    command: list[str]


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return max(minimum, value)


def is_windows() -> bool:
    return os.name == "nt"


def gunicorn_available() -> bool:
    return importlib.util.find_spec("gunicorn") is not None


def on_signal(signum, _frame):
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True
    print(f"[prod] Received signal {signum}, stopping services...")


def build_web_process() -> ProcessSpec:
    host = str(os.getenv("PRODUCTION_WEB_BIND_HOST", "0.0.0.0")).strip() or "0.0.0.0"
    port = env_int("PRODUCTION_WEB_BIND_PORT", 8000, minimum=1)
    web_server = str(os.getenv("PRODUCTION_WEB_SERVER", "auto")).strip().lower() or "auto"

    use_waitress = is_windows() or web_server == "waitress" or (web_server == "auto" and not gunicorn_available())
    if use_waitress:
        threads = env_int("PRODUCTION_WAITRESS_THREADS", 8, minimum=1)
        script = (
            "from waitress import serve; "
            "from config.wsgi import application; "
            f"serve(application, host={host!r}, port={port}, threads={threads})"
        )
        return ProcessSpec(
            name="web(waitress)",
            command=[sys.executable, "-c", script],
        )

    workers = env_int("PRODUCTION_WEB_WORKERS", max(2, os.cpu_count() or 2), minimum=1)
    threads = env_int("PRODUCTION_WEB_THREADS", 2, minimum=1)
    timeout_seconds = env_int("PRODUCTION_WEB_TIMEOUT_SECONDS", 60, minimum=10)
    return ProcessSpec(
        name="web(gunicorn)",
        command=[
            sys.executable,
            "-m",
            "gunicorn",
            "config.wsgi:application",
            "--bind",
            f"{host}:{port}",
            "--workers",
            str(workers),
            "--threads",
            str(threads),
            "--timeout",
            str(timeout_seconds),
        ],
    )


def build_worker_process() -> ProcessSpec:
    loglevel = str(os.getenv("PRODUCTION_CELERY_LOGLEVEL", "INFO")).strip() or "INFO"
    if is_windows():
        return ProcessSpec(
            name="celery-worker",
            command=[
                sys.executable,
                "-m",
                "celery",
                "-A",
                "config",
                "worker",
                "--pool=solo",
                "--concurrency=1",
                f"--loglevel={loglevel}",
                "--hostname=itsm_worker@%h",
            ],
        )

    concurrency = env_int(
        "PRODUCTION_CELERY_WORKER_CONCURRENCY",
        max(2, (os.cpu_count() or 2) // 2),
        minimum=1,
    )
    return ProcessSpec(
        name="celery-worker",
        command=[
            sys.executable,
            "-m",
            "celery",
            "-A",
            "config",
            "worker",
            f"--loglevel={loglevel}",
            "--concurrency",
            str(concurrency),
            "--hostname=itsm_worker@%h",
        ],
    )


def build_beat_process() -> ProcessSpec:
    loglevel = str(os.getenv("PRODUCTION_CELERY_LOGLEVEL", "INFO")).strip() or "INFO"
    schedule_file = CELERY_RUNTIME_DIR / "celerybeat-schedule"
    pid_file = CELERY_RUNTIME_DIR / "celerybeat.pid"
    return ProcessSpec(
        name="celery-beat",
        command=[
            sys.executable,
            "-m",
            "celery",
            "-A",
            "config",
            "beat",
            f"--loglevel={loglevel}",
            "--schedule",
            str(schedule_file),
            "--pidfile",
            str(pid_file),
        ],
    )


def run_prepare_steps(env: dict[str, str], skip_prepare: bool, skip_migrate: bool, skip_collectstatic: bool) -> None:
    if skip_prepare:
        print("[prod] Skip prepare steps.")
        return

    run_migrate = not skip_migrate and env_bool("PRODUCTION_RUN_MIGRATE_ON_START", True)
    run_collectstatic = not skip_collectstatic and env_bool("PRODUCTION_RUN_COLLECTSTATIC_ON_START", True)

    if run_migrate:
        command = [sys.executable, "manage.py", "migrate", "--noinput"]
        print(f"[prod] Running: {' '.join(command)}")
        subprocess.run(command, cwd=BASE_DIR, env=env, check=True)

    if run_collectstatic:
        command = [sys.executable, "manage.py", "collectstatic", "--noinput"]
        print(f"[prod] Running: {' '.join(command)}")
        subprocess.run(command, cwd=BASE_DIR, env=env, check=True)


def terminate_processes(processes: dict[str, subprocess.Popen]) -> None:
    for process in processes.values():
        if process.poll() is None:
            process.terminate()

    deadline = time.time() + 12
    for process in processes.values():
        if process.poll() is not None:
            continue
        timeout = max(0.1, deadline - time.time())
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def start_processes(specs: list[ProcessSpec], env: dict[str, str]) -> dict[str, subprocess.Popen]:
    processes: dict[str, subprocess.Popen] = {}
    for spec in specs:
        print(f"[prod] Starting {spec.name}: {' '.join(spec.command)}")
        process = subprocess.Popen(spec.command, cwd=BASE_DIR, env=env)
        processes[spec.name] = process
    return processes


def supervise(processes: dict[str, subprocess.Popen]) -> int:
    while True:
        if _SHUTDOWN_REQUESTED:
            terminate_processes(processes)
            return 0

        for name, process in processes.items():
            return_code = process.poll()
            if return_code is None:
                continue
            print(f"[prod] {name} exited with code {return_code}, stopping remaining services...")
            terminate_processes(processes)
            return return_code
        time.sleep(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ITSM production stack in one cross-platform process group.")
    parser.add_argument("--skip-prepare", action="store_true", help="Skip migrate and collectstatic.")
    parser.add_argument("--skip-migrate", action="store_true", help="Skip migrate.")
    parser.add_argument("--skip-collectstatic", action="store_true", help="Skip collectstatic.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = os.environ.copy()
    env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    env["DJANGO_ENV"] = "production"
    env["DJANGO_DEBUG"] = "False"
    env.setdefault("PYTHONUNBUFFERED", "1")

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_signal)

    try:
        run_prepare_steps(
            env=env,
            skip_prepare=args.skip_prepare,
            skip_migrate=args.skip_migrate,
            skip_collectstatic=args.skip_collectstatic,
        )
    except subprocess.CalledProcessError as exc:
        print(f"[prod] Prepare step failed with code {exc.returncode}.")
        return exc.returncode

    specs = [build_web_process(), build_worker_process(), build_beat_process()]
    try:
        processes = start_processes(specs, env)
    except OSError as exc:
        print(f"[prod] Failed to start process: {exc}")
        return 1

    try:
        return supervise(processes)
    except KeyboardInterrupt:
        terminate_processes(processes)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
