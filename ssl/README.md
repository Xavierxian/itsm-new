# SSL 证书放置与配置说明

目录结构：
- `ssl/iis`：IIS 证书与配置
- `ssl/tomcat`：Tomcat 证书与配置

## IIS
建议放置：
- `ssl/iis/site.pfx`（包含证书+私钥）

参考配置文件：
- `ssl/iis/web.config.example`

说明：
1. 在 IIS 站点绑定中添加 `https/443`，选择导入的证书。
2. `web.config.example` 里已包含 HTTP 到 HTTPS 跳转和反向代理头透传示例。
3. 如果你的 Django 在反向代理后，保留 `X-Forwarded-Proto: https`。

## Tomcat
建议放置：
- `ssl/tomcat/keystore.p12`（PKCS12 证书）

参考配置文件：
- `ssl/tomcat/server.xml.ssl.example`

说明：
1. 把示例 `Connector` 段复制到 Tomcat 的 `conf/server.xml`。
2. 替换 `certificateKeystoreFile`、`certificateKeystorePassword`。
3. 重启 Tomcat 生效。

## 安全建议
- 不要把真实密码提交到 Git。
- 生产环境请限制证书文件权限，仅允许服务账户读取。
