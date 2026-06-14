import os
import dash
from datetime import timedelta
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix
from lightshowai.auth import init_auth
from services.redis_store import redis_client
import redis

app = dash.Dash(
    prevent_initial_callbacks=True, 
    title="OmniXAS@Lightshow.ai",
    url_base_pathname="/omnixas/"
)
server = app.server
server.wsgi_app = ProxyFix(server.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Flask secret key — required for signing session cookies
_flask_secret = os.environ.get("FLASK_SECRET_KEY")
if not _flask_secret:
    raise RuntimeError("FLASK_SECRET_KEY is not set")

server.config.update(
    SECRET_KEY=_flask_secret,
    # Server-side sessions stored in Redis
    SESSION_TYPE="redis",
    SESSION_REDIS=redis_client,
    SESSION_KEY_PREFIX="omnixas:session:",   # namespace to avoid collisions
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    SESSION_USE_SIGNER=True,                  # sign the session ID cookie
    # Cookie hardening
    SESSION_COOKIE_NAME="omnixas_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("OMNIXAS_COOKIE_SECURE", "true").lower() == "true",
)

Session(server)
init_auth(server)

# return amount of visitors, and update count
@server.route("/visitor-count")
def _visitor_count():
    try:
        count = redis_client.incr("app:visitor_count")

    except redis.RedisError as e:
        print(f"Redis error: {e}")
        return '{"error": "Database unavailable"}', 503, {"Content-Type": "application/json"}

    return f'{{"count": {count}}}', 200, {"Content-Type": "application/json"}
