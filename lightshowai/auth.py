"""
OIDC authentication for LightshowAI.

This module registers an Authlib OAuth client against an OIDC provider
(Entra AD by default, but any OIDC-compliant IdP via the discovery URL).

Environment variables required:
    OIDC_DISCOVERY_URL   - The provider's .well-known/openid-configuration URL
    OIDC_CLIENT_ID       - Client ID from the IdP app registration
    OIDC_CLIENT_SECRET   - Client secret from the IdP app registration
    OIDC_REDIRECT_URI    - Callback URL registered with the IdP
                           (e.g., https://host/auth/callback)
"""

import os
from authlib.integrations.flask_client import OAuth


# Module-level handle to the registered client. Populated by init_auth().
# Other modules (and later steps) import `oauth` from here to trigger the flow.
oauth = OAuth()


def init_auth(server):
    """
    Initialize OIDC authentication on the given Flask server.

    Must be called after Flask-Session is set up (so `server.config` already
    has SECRET_KEY and session backend configured).

    Args:
        server: The Flask application instance.
    """
    required_vars = [
        "OIDC_DISCOVERY_URL",
        "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET",
        "OIDC_REDIRECT_URI",
    ]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f"OIDC configuration incomplete. Missing env vars: {', '.join(missing)}"
        )

    # Copy OIDC config onto Flask config so Authlib can read it.
    server.config["OIDC_CLIENT_ID"] = os.environ["OIDC_CLIENT_ID"]
    server.config["OIDC_CLIENT_SECRET"] = os.environ["OIDC_CLIENT_SECRET"]
    server.config["OIDC_DISCOVERY_URL"] = os.environ["OIDC_DISCOVERY_URL"]
    server.config["OIDC_REDIRECT_URI"] = os.environ["OIDC_REDIRECT_URI"]

    oauth.init_app(server)

    # Register the OIDC provider. The name "oidc" is how we'll reference it
    # later: oauth.oidc.authorize_redirect(...), oauth.oidc.authorize_access_token(...)
    oauth.register(
        name="oidc",
        client_id=server.config["OIDC_CLIENT_ID"],
        client_secret=server.config["OIDC_CLIENT_SECRET"],
        server_metadata_url=server.config["OIDC_DISCOVERY_URL"],
        client_kwargs={
            "scope": "openid profile email",
            # Explicit response type for clarity; "code" is the authorization
            # code flow, which is what we want for a server-side web app.
            "response_type": "code",
        },
    )

    print(f"OIDC client registered against discovery URL: "
          f"{server.config['OIDC_DISCOVERY_URL']}")