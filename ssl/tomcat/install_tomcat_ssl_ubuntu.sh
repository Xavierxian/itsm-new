#!/usr/bin/env bash
set -euo pipefail

# 用法：
# 1) 把 baison.net.jks 放到 /opt/itsm-new/ssl/tomcat/
# 2) export TOMCAT_SSL_PASSWORD='你的证书密码'
# 3) sudo bash ssl/tomcat/install_tomcat_ssl_ubuntu.sh

APP_DIR="/opt/itsm-new"
CERT_FILE="$APP_DIR/ssl/tomcat/baison.net.jks"
TOMCAT_CONF=""

if [[ -f /etc/tomcat10/server.xml ]]; then
  TOMCAT_CONF="/etc/tomcat10/server.xml"
elif [[ -f /etc/tomcat9/server.xml ]]; then
  TOMCAT_CONF="/etc/tomcat9/server.xml"
elif [[ -n "${CATALINA_BASE:-}" && -f "$CATALINA_BASE/conf/server.xml" ]]; then
  TOMCAT_CONF="$CATALINA_BASE/conf/server.xml"
else
  echo "[ERROR] 未找到 Tomcat server.xml，请手动设置 TOMCAT_CONF" >&2
  exit 1
fi

if [[ ! -f "$CERT_FILE" ]]; then
  echo "[ERROR] 证书文件不存在: $CERT_FILE" >&2
  exit 1
fi

if [[ -z "${TOMCAT_SSL_PASSWORD:-}" ]]; then
  echo "[ERROR] 请先 export TOMCAT_SSL_PASSWORD='证书密码'" >&2
  exit 1
fi

TMP_SNIPPET="$(mktemp)"
cat > "$TMP_SNIPPET" <<EOF
<Connector
    port="443"
    protocol="org.apache.coyote.http11.Http11NioProtocol"
    SSLEnabled="true"
    maxThreads="200"
    scheme="https"
    secure="true"
    clientAuth="false"
    sslProtocol="TLS"
    URIEncoding="UTF-8"
    connectionTimeout="20000"
    redirectPort="443">
    <SSLHostConfig>
        <Certificate
            certificateKeystoreType="JKS"
            certificateKeystoreFile="$CERT_FILE"
            certificateKeystorePassword="$TOMCAT_SSL_PASSWORD"
            type="RSA" />
    </SSLHostConfig>
</Connector>
EOF

if grep -q 'port="443"' "$TOMCAT_CONF"; then
  echo "[INFO] 检测到已有 443 Connector，请手动检查避免重复: $TOMCAT_CONF"
else
  cp "$TOMCAT_CONF" "$TOMCAT_CONF.bak.$(date +%Y%m%d%H%M%S)"
  awk -v snippet="$TMP_SNIPPET" '
    /<Service[[:space:]][^>]*name="Catalina"/ {print; in_service=1; next}
    in_service && /<Connector[[:space:]][^>]*port="8080"/ && !inserted {
      print
      while ((getline line < snippet) > 0) print line
      close(snippet)
      inserted=1
      next
    }
    {print}
  ' "$TOMCAT_CONF" > "$TOMCAT_CONF.new"
  mv "$TOMCAT_CONF.new" "$TOMCAT_CONF"
  echo "[OK] 已写入 443 SSL Connector: $TOMCAT_CONF"
fi

if command -v ufw >/dev/null 2>&1; then
  ufw allow 443/tcp || true
fi

if systemctl list-unit-files | grep -q '^tomcat10\.service'; then
  systemctl restart tomcat10
elif systemctl list-unit-files | grep -q '^tomcat9\.service'; then
  systemctl restart tomcat9
else
  echo "[WARN] 未识别 tomcat9/tomcat10 服务名，请手动重启 Tomcat"
fi

echo "[DONE] HTTPS 配置完成，请访问: https://你的域名"
