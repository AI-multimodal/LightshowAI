#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/.local/logs"
SSL_DIR="$PROJECT_ROOT/.local/ssl"
APACHE_TEMPLATE="$PROJECT_ROOT/deploy/apache/lightshowai-local.conf.template"
APACHE_RENDERED="$PROJECT_ROOT/.local/lightshowai-local-macos.conf"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install from https://brew.sh"
  exit 1
fi

if ! brew list httpd >/dev/null 2>&1; then
  echo "Installing Homebrew Apache (httpd)..."
  brew install httpd
fi

mkdir -p "$LOG_DIR/apache2"
mkdir -p "$SSL_DIR"

if [ ! -f "$SSL_DIR/cert.pem" ] || [ ! -f "$SSL_DIR/key.pem" ]; then
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SSL_DIR/key.pem" \
    -out "$SSL_DIR/cert.pem" \
    -subj "/C=US/ST=NY/L=Upton/O=Local/OU=Dev/CN=localhost"
fi

# Render from template and switch to a non-privileged TLS port for macOS.
sed \
  -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
  -e "s|{{LOG_DIR}}|$LOG_DIR|g" \
  -e "s|{{SSL_DIR}}|$SSL_DIR|g" \
  -e "s|<VirtualHost \*:443>|<VirtualHost *:8444>|g" \
  "$APACHE_TEMPLATE" > "$APACHE_RENDERED"

cat >> "$APACHE_RENDERED" <<EOF

<VirtualHost *:8445>
    ServerName localhost

    SSLEngine on
    SSLCertificateFile $SSL_DIR/cert.pem
    SSLCertificateKeyFile $SSL_DIR/key.pem

    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"

    ProxyPass        / http://127.0.0.1:8000/
    ProxyPassReverse / http://127.0.0.1:8000/

    ErrorLog  $LOG_DIR/apache2/chatbot_error.log
    CustomLog $LOG_DIR/apache2/chatbot_access.log combined
</VirtualHost>
EOF

HOMEBREW_PREFIX="$(brew --prefix)"
HTTPD_PREFIX="$(brew --prefix httpd)"
HTTPD_CONF="$HOMEBREW_PREFIX/etc/httpd/httpd.conf"
HTTPD_BIN="$HTTPD_PREFIX/bin/httpd"

if [ ! -f "$HTTPD_CONF" ]; then
  echo "Could not find Homebrew Apache config at: $HTTPD_CONF"
  exit 1
fi

ensure_line() {
  local line="$1"
  local file="$2"
  if ! grep -Fq "$line" "$file"; then
    echo "$line" >> "$file"
  fi
}

uncomment_or_append() {
  local line="$1"
  local file="$2"
  if grep -Fq "#$line" "$file"; then
    sed -i '' "s|^#${line}$|${line}|" "$file"
  elif ! grep -Fq "$line" "$file"; then
    echo "$line" >> "$file"
  fi
}

# Ensure required modules are loaded before the included vhost config is parsed.
uncomment_or_append "LoadModule ssl_module lib/httpd/modules/mod_ssl.so" "$HTTPD_CONF"
uncomment_or_append "LoadModule proxy_module lib/httpd/modules/mod_proxy.so" "$HTTPD_CONF"
uncomment_or_append "LoadModule proxy_http_module lib/httpd/modules/mod_proxy_http.so" "$HTTPD_CONF"
uncomment_or_append "LoadModule headers_module lib/httpd/modules/mod_headers.so" "$HTTPD_CONF"
uncomment_or_append "LoadModule socache_shmcb_module lib/httpd/modules/mod_socache_shmcb.so" "$HTTPD_CONF"

# Ensure listen ports for local TLS vhosts.
ensure_line "Listen 8444" "$HTTPD_CONF"
ensure_line "Listen 8445" "$HTTPD_CONF"

# Include generated site config.
ensure_line "Include $APACHE_RENDERED" "$HTTPD_CONF"

"$HTTPD_BIN" -t
brew services restart httpd

echo "Apache configured for macOS (Homebrew httpd)."
echo "Static site: https://localhost:8444/"
echo "Dash app:    https://localhost:8444/omnixas/"
echo "Chatbot:     https://localhost:8445/"
