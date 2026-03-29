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
  "$APACHE_TEMPLATE" > "$APACHE_RENDERED"

sudo cp "$APACHE_RENDERED" /etc/apache2/sites-available/lightshowai-local.conf
sudo a2enmod ssl proxy proxy_http headers
sudo a2ensite lightshowai-local.conf
sudo apache2ctl configtest
sudo service apache2 restart

echo "Apache configured."
echo "Static site: https://localhost/"
echo "Dash app:    https://localhost/omnixas/"