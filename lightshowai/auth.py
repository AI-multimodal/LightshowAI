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
from flask import redirect, url_for, session, jsonify, request

def _register_routes(server):
    """Register /login, /auth/callback, /logout, and /whoami routes."""

    @server.route("/login")
    def login():
        """Kick off the OAuth2 authorization code flow."""
        redirect_uri = server.config["OIDC_REDIRECT_URI"]
        return oauth.oidc.authorize_redirect(redirect_uri)

    @server.route("/auth/callback")
    def auth_callback():
        """
        Handle the redirect back from the IdP.

        Authlib does the heavy lifting here:
        - exchanges the authorization code for tokens
        - validates the ID token signature against JWKS
        - validates issuer, audience, nonce, and expiration
        - parses the ID token claims into a dict

        If any of that fails, authorize_access_token() raises, and Flask
        returns a 500. We can add prettier error handling later.
        """
        token = oauth.oidc.authorize_access_token()

        # The ID token's claims — this is where user identity lives.
        # Typical Entra claims: sub, name, preferred_username, email, oid, tid.
        userinfo = token.get("userinfo") or {}

        # Store a compact user profile in the session. Keep this small —
        # sessions should hold identity, not profile data you can refetch.
        session["user"] = {
            "sub": userinfo.get("sub"),
            "name": userinfo.get("name"),
            "email": userinfo.get("email") or userinfo.get("preferred_username"),
            "oid": userinfo.get("oid"),     # Entra's stable per-user GUID
            "tid": userinfo.get("tid"),     # Entra tenant ID
        }
        session.permanent = True

        # Redirect to wherever the user was trying to go, or the app root.
        next_url = session.pop("next_url", "/omnixas/")
        return redirect(next_url)

    @server.route("/logout")
    def logout():
        """Clear the local session. No IdP round-trip for now."""
        session.clear()
        return redirect("/omnixas/")

    @server.route("/whoami")
    def whoami():
        """Debug route: return the current session's user, if any."""
        user = session.get("user")
        if not user:
            return jsonify({"authenticated": False}), 200
        return jsonify({"authenticated": True, "user": user}), 200


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
    _register_routes(server)  

    print(f"OIDC client registered against discovery URL: "
          f"{server.config['OIDC_DISCOVERY_URL']}")

