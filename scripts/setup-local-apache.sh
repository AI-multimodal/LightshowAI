#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/.local/logs"
SSL_DIR="$PROJECT_ROOT/.local/ssl"
APACHE_TEMPLATE="$PROJECT_ROOT/deploy/apache/lightshowai-local.conf.template"
APACHE_RENDERED="$PROJECT_ROOT/.local/lightshowai-local.conf"

mkdir -p "$LOG_DIR/apache2"
mkdir -p "$SSL_DIR"

if [ ! -f "$SSL_DIR/cert.pem" ] || [ ! -f "$SSL_DIR/key.pem" ]; then
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SSL_DIR/key.pem" \
    -out "$SSL_DIR/cert.pem" \
    -subj "/C=US/ST=NY/L=Upton/O=Local/OU=Dev/CN=localhost"
fi

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

    RewriteEngine On
    RewriteCond %{HTTP:Upgrade} =websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule ^/(.*)$ ws://127.0.0.1:8000/\$1 [P,L]

    ProxyPass        / http://127.0.0.1:8000/
    ProxyPassReverse / http://127.0.0.1:8000/

    ErrorLog  $LOG_DIR/apache2/chatbot_error.log
    CustomLog $LOG_DIR/apache2/chatbot_access.log combined
</VirtualHost>
EOF

if [ -f /etc/apache2/ports.conf ] && [ ! -f /etc/apache2/ports.conf.lightshowai.bak ]; then
  sudo cp /etc/apache2/ports.conf /etc/apache2/ports.conf.lightshowai.bak
fi

printf "Listen 8444\nListen 8445\n" | sudo tee /etc/apache2/ports.conf >/dev/null

sudo cp "$APACHE_RENDERED" /etc/apache2/sites-available/lightshowai-local.conf
sudo a2enmod ssl proxy proxy_http proxy_wstunnel rewrite headers
sudo a2dissite 000-default.conf
sudo a2ensite lightshowai-local.conf
sudo apache2ctl configtest
sudo service apache2 restart

echo "Apache configured."
echo "Static site: https://localhost:8444/"
echo "Dash app:    https://localhost:8444/omnixas/"
echo "Chatbot:     https://localhost:8445/"
