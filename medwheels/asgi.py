import os
from urllib.parse import unquote

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from asgiref.sync import sync_to_async

# --- Django setup (must be before importing Django models) ---
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medwheels.settings')

import django
django.setup()

from django.core.asgi import get_asgi_application
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session

import main.routing

django_asgi_app = get_asgi_application()
User = get_user_model()


# --- Helper: get user from session key ---
@sync_to_async
def _get_user_from_session_key(session_key):
    try:
        sess = Session.objects.get(session_key=session_key)
        data = sess.get_decoded()
        uid = data.get('_auth_user_id')
        if not uid:
            return None
        return User.objects.get(pk=uid)
    except Exception:
        return None


# --- Middleware to restore cookies on Render/Cloudflare ---
class CookieAuthMiddleware:
    """
    Ensures `scope["user"]` is populated for WebSocket connections
    even if proxy strips cookies before Channels parses them.
    Works alongside AuthMiddlewareStack.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "websocket":
            user = scope.get("user")
            if not user or not getattr(user, "is_authenticated", False):
                session_key = None

                # Try parsed cookies first
                cookies = scope.get("cookies") or {}
                if cookies.get("sessionid"):
                    session_key = cookies["sessionid"]

                # Fallback: manually parse raw cookie header
                if not session_key:
                    headers = dict(scope.get("headers") or [])
                    raw_cookie = headers.get(b"cookie")
                    if raw_cookie:
                        for part in raw_cookie.decode("latin1").split(";"):
                            if "=" in part:
                                name, val = part.strip().split("=", 1)
                                if name == "sessionid":
                                    session_key = unquote(val)
                                    break

                # Resolve the user if we found a session
                if session_key:
                    u = await _get_user_from_session_key(session_key)
                    scope["user"] = u or AnonymousUser()
                else:
                    scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)


# --- Application routing ---
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": CookieAuthMiddleware(
        AuthMiddlewareStack(
            URLRouter(main.routing.websocket_urlpatterns)
        )
    ),
})
