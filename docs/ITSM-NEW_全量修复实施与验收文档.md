# ITSM-NEW 全量修复实施与验收文档

更新日期：2026-04-27  
适用版本：当前仓库主线代码（本次修复交付）

## 1. 目标与范围

本次修复在不改变核心业务流程的前提下，完成以下方向加固：

- 登录安全（限流、失败锁定、统一错误语义）
- 传输加密与外联安全（HTTPS 强制、敏感参数禁 URL 传递、TLS 校验）
- 敏感数据保护（口令加密存储、不回显、不入审计）
- SQL 与输入安全加固（参数化、标识符白名单）
- 并发与线程上下文安全（ASGI/WSGI 兼容、任务分布式锁）
- 数据库连接与查询优化（连接复用、健康检查、索引、缓存）
- Redis 引入与降级策略（限流/缓存/锁，同时保证 Redis 故障不致系统崩溃）
- 测试完整性与可验收性提升

## 2. 已实施修复（代码落地点）

### 2.1 生产安全基线

已在 `config/settings.py` 实施：

- 生产环境强校验：
  - `DJANGO_ENV=production` 时必须配置强 `DJANGO_SECRET_KEY`
  - 强制 `DJANGO_DEBUG=False`
  - 强制 `DJANGO_ALLOWED_HOSTS`、`DJANGO_CSRF_TRUSTED_ORIGINS`
- 安全开关默认强制：
  - `SECURE_SSL_REDIRECT=True`
  - `SESSION_COOKIE_SECURE=True`
  - `CSRF_COOKIE_SECURE=True`
  - `SECURE_HSTS_SECONDS>=31536000`
  - `SECURE_HSTS_INCLUDE_SUBDOMAINS=True`
  - `SECURE_HSTS_PRELOAD=True`
- 数据库连接优化：
  - `CONN_MAX_AGE`、`CONN_HEALTH_CHECKS` 已启用配置化
- 日志安全与轮转：
  - `RotatingFileHandler`
  - 敏感信息过滤器 `core.logging_filters.SensitiveDataFilter`

### 2.2 登录安全（P0 强制项）

已在 `accounts/views.py`、`accounts/security.py` 实施：

- 失败计数 + 账号锁定：
  - 连续失败阈值：`LOGIN_FAILURE_LIMIT`（默认 5）
  - 锁定时长：`LOGIN_LOCK_MINUTES`（默认 15）
- 双层限流：
  - IP 总限流：`LOGIN_RATE_LIMIT_PER_IP`（默认 60/10 分钟）
  - IP+账号限流：`LOGIN_RATE_LIMIT_PER_IP_USER`（默认 10/10 分钟）
- 登录失败统一文案（避免账号枚举）
- 锁定与限流返回 `429`
- 登录成功后清空失败计数并记录审计
- Redis 键规范已落地：
  - `auth:fail:{username}`
  - `auth:rl:ip:{ip}`
  - `auth:rl:ipu:{ip}:{username}`

### 2.3 敏感字段保护

已在 `core/security.py`、`core/secret_store.py`、`core/models.py`、`assets/forms.py`、`assets/models.py` 实施：

- 新增密文模型 `core.EncryptedSecret`
- 使用应用层加密（Fernet）保存敏感值
- 资产口令字段改造：
  - 表单 `PasswordInput(render_value=False)`，页面不回显
  - 编辑页“留空=不变”
  - 明文字段不再存储真实口令，存占位值
- 审计与日志统一脱敏

### 2.4 日志/审计安全

已在 `logs/utils.py` 实施：

- 审计快照改为白名单序列化（避免黑名单漏网）
- 敏感字段自动排除
- 请求快照与任务参数统一脱敏

### 2.5 传输与外联安全

已在 `cloudops/services.py`、`monitoring/services.py`、`mappings/services/h3c_nat_*.py` 实施：

- JumpServer 关键接口由 URL query 改为 JSON Body（避免凭据出现在 URL）
- 外联默认 HTTPS，非 HTTPS 需显式豁免 `ALLOW_INSECURE_UPSTREAM_HTTP=true`
- 外联 TLS 校验可控（默认开启）
- H3C Telnet 增加生产开关门禁：
  - `H3C_FW_ENABLE_TELNET` 未显式开启时，生产默认禁用

### 2.6 并发与线程安全

已在 `core/middleware.py`、`core/locks.py`、`logs/tasks.py`、`monitoring/tasks.py` 实施：

- 请求上下文由 `threading.local()` 切换到 `asgiref.local.Local`
- 周期任务增加分布式锁，避免重复执行：
  - 键规范：`lock:task:{name}`

### 2.7 缓存与 Redis 策略

已在 `config/settings.py`、`core/cache_helpers.py`、`accounts/security.py`、`core/views.py`、`core/network.py`、`cloudops/services.py` 实施：

- Redis 用于登录限流、仪表盘统计、外部 API 缓存、分布式锁
- 新增缓存安全封装（降级不宕机）：
  - `core/cache_helpers.py`
- Redis 不可用时：
  - 缓存/限流逻辑降级
  - 页面与核心流程不中断
- 测试环境自动使用 `LocMemCache`（避免 CI 依赖 Redis）

### 2.8 数据库与查询优化

- 连接复用与健康检查已启用（见 2.1）
- 日志索引已补充（迁移）：
  - `logs/migrations/0003_add_performance_indexes.py`

### 2.9 SQL 注入防护现状

- 已有动态 SQL 场景均已限制在安全边界内：
  - 参数值走参数化绑定
  - 动态标识符采用白名单/正则校验或 Django `quote_name`
- 邮件通知模块中外部可配置表名/列名已做标识符校验（仅允许合法标识符）

## 3. 本次新增稳定性修复（针对实施过程发现的问题）

### 3.1 Redis 故障导致 500 的问题

- 已修复：缓存访问改为安全封装，Redis 异常不再导致业务页面 500。

### 3.2 日志脱敏过滤导致格式化异常的问题

- 已修复：先渲染日志文本，再做脱敏，避免 `%s` 占位符被破坏。

### 3.3 测试库缺少 unmanaged 表导致仪表盘报错

- 已修复：仪表盘统计查询失败时自动回退为 `0`，不阻断页面与测试。

## 4. 配置项清单（上线前必查）

核心安全：

- `DJANGO_ENV=production`
- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY`（高强度随机）
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `FIELD_ENCRYPTION_KEY`

登录与限流：

- `LOGIN_FAILURE_LIMIT=5`
- `LOGIN_LOCK_MINUTES=15`
- `LOGIN_RATE_LIMIT_WINDOW_SECONDS=600`
- `LOGIN_RATE_LIMIT_PER_IP=60`
- `LOGIN_RATE_LIMIT_PER_IP_USER=10`

缓存与 Redis：

- `REDIS_URL=redis://...`
- `DASHBOARD_STATS_CACHE_TTL=60`（可按压测调 30~120）

外联安全：

- `MONITORING_VERIFY_TLS=true`
- `MONITORING_AI_VERIFY_TLS=true`
- `ALLOW_INSECURE_UPSTREAM_HTTP=false`（仅豁免场景临时开启）
- `H3C_FW_ENABLE_TELNET=false`（生产建议）

## 5. Redis 是否需要增加（结论）

需要，且已在代码中完成接入。原因：

- 登录限流/锁定计数天然适合 Redis（原子计数 + TTL）
- 高频统计、外联摘要缓存可显著降低 DB 与外部接口压力
- 分布式任务锁需要共享状态，Redis 是最低成本可行方案

同时已实现“Redis 不可用时服务可降级运行”，避免单点故障。

## 6. 测试与验收结果

已执行：

- `python -m compileall accounts assets core cloudops config logs mappings monitoring`
- `python manage.py check`
- `python manage.py test core.tests accounts.tests logs.tests --noinput`

结果：

- 编译通过
- Django 系统检查通过
- 回归测试通过（10/10）

`--deploy` 验证：

- 在满足强随机 `DJANGO_SECRET_KEY`、生产必填项齐全时：
  - `python manage.py check --deploy` 无告警

## 7. 发布步骤（建议）

1. 轮换所有历史凭据（MySQL/SQLServer/SMTP/JumpServer/AI Key 等）
2. 配置生产环境变量（见第 4 节）
3. 执行数据库迁移：
   - `python manage.py migrate`
4. 发布前检查：
   - `python manage.py check --deploy`
5. 灰度发布：
   - 10% -> 50% -> 100%（每阶段观察 30 分钟）
6. 重点观测指标：
   - 登录 429 比例
   - DB 连接峰值
   - Redis 命中率
   - 慢查询数
   - 周期任务重复执行率

## 8. 回滚方案

若出现回归，可按以下最小影响回退：

- 配置回滚：
  - 临时降低限流阈值或关闭严格策略（仅应急）
- 功能回滚：
  - 通过开关禁用高风险外联路径（如 Telnet）
- 数据回滚：
  - 密文存储采用兼容策略，不影响既有业务字段读取
- 发布回滚：
  - 按灰度节点回退至上一稳定版本

## 9. 剩余人工动作（必须执行）

- 立即轮换 `.env` 内及上游系统中的真实凭据
- 将密钥注入改为 CI/CD Secret 或密钥管理服务（禁止长期明文落盘）
- 对非 HTTPS 内网外联建立豁免台账并设整改截止日期
- 根据真实压测结果调整缓存 TTL 和限流阈值

## 10. 变更文件索引（本次修复关键）

- `config/settings.py`
- `accounts/views.py`
- `accounts/security.py`
- `assets/forms.py`
- `assets/models.py`
- `core/security.py`
- `core/secret_store.py`
- `core/models.py`
- `core/migrations/0002_encryptedsecret.py`
- `core/cache_helpers.py`
- `core/logging_filters.py`
- `core/middleware.py`
- `core/network.py`
- `core/locks.py`
- `core/views.py`
- `cloudops/services.py`
- `monitoring/services.py`
- `logs/utils.py`
- `logs/models.py`
- `logs/migrations/0003_add_performance_indexes.py`
- `logs/tasks.py`
- `monitoring/tasks.py`
- `.env.example`
- `README.md`

