# ITSM Platform

企业内部 ITSM 平台（Django 5 + MySQL + Redis + Celery）。

## 快速启动
1. 创建并激活虚拟环境。
2. 安装依赖：`pip install -r requirements.txt`
3. 复制环境变量模板：`.env.example` -> `.env`
4. 配置数据库与 Redis。
5. 执行迁移：`python manage.py migrate`
6. 创建管理员：`python manage.py createsuperuser`
7. 启动服务：`python manage.py runserver`

## 生产运行（Windows/Linux 通用）
- 统一入口：`python scripts/production_runner.py`
- 该入口会按配置自动执行 `migrate`、`collectstatic`，并拉起：
  - Django Web（Linux 优先 Gunicorn，Windows 使用 Waitress）
  - Celery Worker
  - Celery Beat
- 默认启用 WhiteNoise 静态文件服务（无 Nginx 也可运行）。
- 该入口会强制使用 `DJANGO_ENV=production` 与 `DJANGO_DEBUG=False`。

### Linux 常驻（systemd）
1. 根据实际路径修改 `deploy/systemd/itsm-all.service`。
2. 安装服务：
   - `sudo cp deploy/systemd/itsm-all.service /etc/systemd/system/itsm-all.service`
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable --now itsm-all`
3. 查看日志：`journalctl -u itsm-all -f`

### Windows 常驻（任务计划）
1. 管理员 PowerShell 执行：`./deploy/windows/install-startup-task.ps1`
2. 启动脚本：`deploy/windows/start-itsm-prod.ps1`
3. 卸载任务：`./deploy/windows/uninstall-startup-task.ps1`

## 调度器自动启动
- 开发环境下执行 `python manage.py runserver` 时，项目会自动启动 Celery `worker+beat`（用于执行定时任务）。
- 默认开关：`AUTO_START_CELERY_ON_RUNSERVER=True`。
- 如需关闭自动启动：设置 `AUTO_START_CELERY_ON_RUNSERVER=False`。
- 该自动启动机制依赖 Redis（`REDIS_URL` 或 `REDIS_HOST` 已配置）。

## 安全基线
- 生产环境必须设置：`DJANGO_ENV=production`。
- 生产必须显式提供：`DJANGO_ALLOWED_HOSTS`、`DJANGO_CSRF_TRUSTED_ORIGINS`。
- 建议开启：`DJANGO_SECURE_SSL_REDIRECT=True`、`DJANGO_SESSION_COOKIE_SECURE=True`、`DJANGO_CSRF_COOKIE_SECURE=True`。
- 建议配置：`FIELD_ENCRYPTION_KEY`（Fernet key）用于敏感字段加密。
- 建议开启：`SERVE_STATIC_WITH_DJANGO=True`（无 Nginx 时）。
- 默认启用登录失败计数、账号锁定与基于 Redis 的登录限流。

## 注意
- 项目支持 Redis 缓存与 Celery broker/backend。
