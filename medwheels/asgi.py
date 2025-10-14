import os
import json
import django
from urllib.parse import parse_qs

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medwheels.settings')
django.setup()  # ensure ORM ready for sync_to_async use

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.sessions import SessionMiddlewareStack
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from asgiref.sync import sync_to_async

import main.routing

django_asgi_app = get_asgi_application()
User = get_user_model()

@sync_to_async
def get_user_from_session_key(session_key):
    """
    Sync DB access wrapped with sync_to_async.
    Returns a User instance or None.
    """
    try:
        sess = Session.objects.get(session_key=session_key)
    except Session.DoesNotExist:
        return None
    data = sess.get_decoded()
    uid = data.get('_auth_user_id')
    if not uid:
        return None
    try:
        return User.objects.get(pk=uid)
    except User.DoesNotExist:
        return None

class EnsureScopeUserMiddleware:
    """
    ASGI middleware that ensures scope['user'] is populated even if Channels
    did not parse cookies into scope['cookies'] (robust for proxies).
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Only run for websocket connections
        if scope.get('type') == 'websocket':
            # If Channels/session middleware already populated user, keep it
            if scope.get('user') and getattr(scope.get('user'), 'is_authenticated', False):
                return await self.inner(scope, receive, send)

            # 1) Try scope['cookies'] first (Channels may already have parsed)
            session_key = None
            cookies = scope.get('cookies') or {}
            if cookies.get('sessionid'):
                session_key = cookies.get('sessionid')

            # 2) If no cookies, try to find a `cookie` header and parse it
            if not session_key:
                headers = scope.get('headers') or []
                cookie_header = None
                for (hk, hv) in headers:
                    if hk.lower() == b'cookie':
                        cookie_header = hv.decode('latin1')
                        break
                if cookie_header:
                    # parse "a=1; b=2" -> dict
                    for part in cookie_header.split(';'):
                        part = part.strip()
                        if not part:
                            continue
                        name, sep, val = part.partition('=')
                        if name == 'sessionid' and val:
                            session_key = val
                            break

            # 3) If we have a session key, load the user
            if session_key:
                user = await get_user_from_session_key(session_key)
                if user:
                    scope['user'] = user
                else:
                    scope['user'] = AnonymousUser()
            else:
                scope['user'] = AnonymousUser()

        return await self.inner(scope, receive, send)

# Wrap URLRouter with standard SessionMiddlewareStack and our EnsureScopeUserMiddleware
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": SessionMiddlewareStack(
        EnsureScopeUserMiddleware(
            URLRouter(main.routing.websocket_urlpatterns)
        )
    ),
})
