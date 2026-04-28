# Security Remediation Status

## Implemented in code
- Production security baseline hardening in `config/settings.py`:
  - Enforced production checks for `DJANGO_ENV`, `SECRET_KEY`, `DEBUG`.
  - Production-forced secure cookies, HTTPS redirect, HSTS.
  - DB connection reuse and health checks.
  - Rotating application logs + sensitive-data logging filter.
- Login hardening in `accounts/views.py` + `accounts/security.py`:
  - Redis/cache-backed rate limiting (IP and IP+user).
  - Account failure counting and lockout.
  - Unified login error semantics.
  - 429 on lock/rate-limit.
- Sensitive data protection:
  - Added encrypted secret store model: `core.EncryptedSecret`.
  - Added secret encryption utilities (`core/security.py`, `core/secret_store.py`).
  - Asset forms now do no password re-display and persist encrypted values.
  - Audit serialization switched to whitelist + sensitive field exclusion.
- Transport and external calls:
  - JumpServer token request changed from query to JSON body.
  - Credential password update changed from query to JSON body.
  - TLS verification and HTTPS policy checks for monitoring/jumpserver clients.
  - Added production Telnet disable gate for H3C sync/apply.
- Concurrency and task safety:
  - Request context switched to ASGI-safe local storage.
  - Shared network IP cache moved to Django cache.
  - Added distributed cache locks for periodic tasks.
- Performance:
  - Dashboard count caching via Redis/cache.
  - Added log table indexes migration (`logs.0003_add_performance_indexes`).
- Tests:
  - Added login lock/rate-limit tests.
  - Added serialization sensitive-field exclusion test.
  - Added cache-failure safe fallback in key modules (accounts/core/cloudops).

## Full implementation document
- See `docs/ITSM-NEW_全量修复实施与验收文档.md` for the complete rollout/acceptance/runbook.

## Required manual operations
- Rotate all leaked credentials/secrets in `.env` and upstream systems.
- Apply DB migrations:
  - `python manage.py migrate`
- Ensure Redis is reachable in target environments.
- Set production env values from `.env.example` secure defaults.

## Verification commands
- `python -m compileall accounts assets core cloudops config logs mappings monitoring`
- `python manage.py check`
- `python manage.py check --deploy` (run with production env vars)
- `python manage.py test accounts.tests logs.tests --noinput`
