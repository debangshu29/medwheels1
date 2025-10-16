import os
import django
from urllib.parse import unquote

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from asgiref.sync import sync_to_async

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medwheels.settings')
django.setup()

from django.core.asgi import get_asgi_application
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session

import main.routing

django_asgi_app = get_asgi_application()
User = get_user_model()


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


class CookieSessionAuthMiddleware:
    """
    Middleware that ensures cookies are parsed and user is restored from sessionid.
    Works even when ASGI scope.cookies is None (e.g. Render/Cloudflare proxying).
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "websocket":
            headers = dict(scope.get("headers") or [])
            cookie_header = headers.get(b"cookie", b"").decode("latin1")

            cookies = {}
            if cookie_header:
                for part in cookie_header.split(";"):
                    if "=" in part:
                        name, val = part.strip().split("=", 1)
                        cookies[name] = unquote(val)

            # inject cookies so AuthMiddlewareStack can use them
            scope["cookies"] = cookies

            # Now manually authenticate user if not set
            user = scope.get("user")
            if not user or not getattr(user, "is_authenticated", False):
                session_key = cookies.get("sessionid")
                if session_key:
                    u = await _get_user_from_session_key(session_key)
                    scope["user"] = u or AnonymousUser()
                else:
                    scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": CookieSessionAuthMiddleware(
        AuthMiddlewareStack(
            URLRouter(main.routing.websocket_urlpatterns)
        )
    ),
})
