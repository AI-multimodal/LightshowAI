# Local Setup on macOS

This guide is a macOS copy of the local setup instructions, updated to run LightshowAI on a MacBook.

## Overview

You can run locally in two ways:

- Recommended for development: run Dash directly (no Apache).
- Optional parity mode: run Apache with reverse proxy so URLs match production-style paths.

Recommended flow:

1. Start Dash locally.
2. Open http://127.0.0.1:8443/omnixas/

Optional Apache flow:

1. Start Dash locally on 127.0.0.1:8443.
2. Start Apache (Homebrew httpd) on https://localhost:8444.
3. Apache serves html index and proxies /omnixas/ to Dash.
4. Apache exposes the chatbot on https://localhost:8445/ for secure iframe embedding.

## Repo structure used by local setup

Important folders:

- html/ (static site files)
- lightshowai/ (Dash app code)
- deploy/apache/ (Apache config template)
- scripts/ (helper scripts)
- docs/ (documentation)

Important files:

- scripts/run-xas-local.sh
- deploy/apache/lightshowai-local.conf.template
- .env.example
- .env.local (local only, do not commit)

## Prerequisites (macOS)

- Homebrew installed
- A Python 3.11 environment (conda or venv)
- Command Line Tools installed (xcode-select --install)

## Required environment variables

Create a local env file in the repo root:

    cp .env.example .env.local

Set these values in .env.local:

    TILED_URL=...
    TILED_API_KEY=...
    XAS_SANDBOX_URL=...
    FLASK_SECRET_KEY=replace-with-a-random-secret

Optional (if embedding chatbot in the 4th column):

    OMNIXAS_CHATBOT_URL=https://localhost:8445/

Do not commit .env.local.

## One-time setup

### 1. Activate your Python environment

Conda example:

    conda create -n LightshowAI python=3.11 -y
    conda activate LightshowAI

### 2. Install project dependencies

From repo root:

    pip install -e .

### 3. Make helper scripts executable

From repo root:

    chmod +x scripts/run-xas-local.sh

## Start Dash app (recommended path)

From repo root:

    conda activate LightshowAI
    ./scripts/run-xas-local.sh

If startup succeeds, open:

- http://127.0.0.1:8443/omnixas/

Notes:

- The app binds to 127.0.0.1:8443 by default.
- Keep this terminal open while testing.

## Optional: Apache reverse proxy on macOS

The Linux helper script scripts/setup-local-apache.sh uses Ubuntu tools (a2enmod, a2ensite, /etc/apache2/sites-available, service apache2) and is not directly compatible with macOS.

Use Homebrew Apache (httpd) instead.

### 1. Install Apache and openssl

    brew install httpd openssl

### 2. Create local folders and cert

From repo root:

    mkdir -p .local/logs/apache2 .local/ssl
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout .local/ssl/key.pem \
      -out .local/ssl/cert.pem \
      -subj "/C=US/ST=NY/L=Upton/O=Local/OU=Dev/CN=localhost"

### 3. Render the Apache config template

From repo root:

    PROJECT_ROOT="$(pwd)"
    LOG_DIR="$PROJECT_ROOT/.local/logs"
    SSL_DIR="$PROJECT_ROOT/.local/ssl"
    sed \
      -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
      -e "s|{{LOG_DIR}}|$LOG_DIR|g" \
      -e "s|{{SSL_DIR}}|$SSL_DIR|g" \
      deploy/apache/lightshowai-local.conf.template > .local/lightshowai-local.conf

### 4. Adapt the VirtualHost port for macOS

Edit .local/lightshowai-local.conf and change:

- <VirtualHost *:443> to <VirtualHost *:8444>

Reason: macOS port 443 usually needs root and may conflict with system services.

### 5. Include this config in Homebrew httpd

Find Homebrew Apache config file:

    brew --prefix httpd

Usually this is:

    /opt/homebrew/etc/httpd/httpd.conf

Add these lines if missing:

    LoadModule ssl_module lib/httpd/modules/mod_ssl.so
    LoadModule proxy_module lib/httpd/modules/mod_proxy.so
    LoadModule proxy_http_module lib/httpd/modules/mod_proxy_http.so
    LoadModule headers_module lib/httpd/modules/mod_headers.so
    Include /ABSOLUTE/PATH/TO/REPO/.local/lightshowai-local.conf

Also ensure these listens exist:

    Listen 8080
    Listen 8444

### 6. Start Homebrew Apache

    brew services start httpd

Validate config:

    /opt/homebrew/bin/httpd -t

### 7. Start Dash app in a separate terminal

    conda activate LightshowAI
    cd /Users/ozgurkilic/Projects/AmSC/LightShow_AI/NewGUI/LightshowAI
    ./scripts/run-xas-local.sh

### 8. Open in browser

- https://localhost:8444/
- https://localhost:8444/omnixas/
- https://localhost:8445/

If you are using the embedded chatbot column, set this in .env.local:

    OMNIXAS_CHATBOT_URL=https://localhost:8445/

Reason: browsers block a plain HTTP iframe such as http://localhost:8000 when the main site is loaded over HTTPS.

## Troubleshooting

### Port already in use

If 8443, 8444, or 8445 is busy:

    lsof -nP -iTCP:8443 -sTCP:LISTEN
    lsof -nP -iTCP:8444 -sTCP:LISTEN
    lsof -nP -iTCP:8445 -sTCP:LISTEN

Stop conflicting process or change ports.

### Missing FLASK_SECRET_KEY

If app fails on startup, set FLASK_SECRET_KEY in .env.local.

Generate one quickly:

    python -c "import secrets; print(secrets.token_urlsafe(32))"

### App starts but /omnixas/ is blank

- Confirm Dash is running on 127.0.0.1:8443.
- If using Apache, confirm ProxyPass points to http://127.0.0.1:8443/omnixas/.

### Redis/auth issues

The app expects Redis-backed sessions in some configurations. For local-only testing, ensure your local environment variables match your local runtime assumptions, or run the same local services used by your team setup.

## Summary

For most MacBook development, use the direct Dash path:

1. conda activate LightshowAI
2. ./scripts/run-xas-local.sh
3. Open http://127.0.0.1:8443/omnixas/

Use the Apache section only when you specifically need the local reverse-proxy behavior.
