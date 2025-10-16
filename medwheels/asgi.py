import os
import django
from urllib.parse import unquote

from django.core.asgi import get_asgi_application
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from asgiref.sync import sync_to_async
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

import main.routing

# --- Django setup ---
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medwheels.settings')
django.setup()

django_asgi_app = get_asgi_application()
User = get_user_model()

# --- Helper: load user from session key ---
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


# --- Custom middleware for Render/Cloudflare cookie loss ---
class CookieAuthMiddleware:
    """
    Ensures `scope["user"]` and `scope["session"]` are populated for WebSocket
    connections even when ASGI doesn't parse cookies automatically.
    Works alongside AuthMiddlewareStack.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "websocket":
            # Only replace user if missing or anonymous
            user = scope.get("user")
            if not user or not getattr(user, "is_authenticated", False):
                session_key = None

                # Try reading parsed cookies (if any)
                cookies = scope.get("cookies") or {}
                if cookies.get("sessionid"):
                    session_key = cookies["sessionid"]

                # If no parsed cookies, parse raw cookie header
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

                # Resolve user from session key
                if session_key:
                    u = await _get_user_from_session_key(session_key)
                    if u:
                        scope["user"] = u
                    else:
                        scope["user"] = AnonymousUser()
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
