import os
import logging
from urllib.parse import unquote

# set DJANGO_SETTINGS_MODULE first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medwheels.settings')

import django
django.setup()  # MUST call before importing Django models

from django.core.asgi import get_asgi_application
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.models import Session

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

import main.routing

logger = logging.getLogger("medwheels.asgi")
logger.setLevel(logging.INFO)

django_asgi_app = get_asgi_application()
User = get_user_model()


@sync_to_async
def _user_from_session_key(session_key):
    """
    Sync DB access to read session and resolve user id.
    Returns (user instance or None, debug_message)
    """
    try:
        sess = Session.objects.get(session_key=session_key)
    except Session.DoesNotExist:
        return None, f"no session with key {session_key!r}"
    try:
        data = sess.get_decoded()
    except Exception as e:
        return None, f"session decode failed: {e}"
    uid = data.get('_auth_user_id')
    if not uid:
        return None, f"session {session_key!r} has no _auth_user_id"
    try:
        u = User.objects.get(pk=uid)
        return u, f"resolved user id={uid}"
    except User.DoesNotExist:
        return None, f"user id {uid} not found"


class RobustCookieAuthMiddleware:
    """
    Middleware for websockets that:
      - ensures scope['cookies'] is present (parsed),
      - tries to resolve a logged-in user from sessionid header if scope['user']
        is anonymous/missing,
      - logs helpful debug messages so we know what went wrong.
    Wraps AuthMiddlewareStack in the application below.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Only operate on websocket connections
        if scope.get('type') == 'websocket':
            # 1) Ensure scope['cookies'] exists by parsing cookie header if needed
            cookies = scope.get('cookies')
            if not cookies:
                cookies = {}
                headers = scope.get('headers') or []
                for (hk, hv) in headers:
                    if hk.lower() == b'cookie':
                        try:
                            raw = hv.decode('latin1')
                        except Exception:
                            raw = hv.decode('utf-8', 'ignore')
                        # parse "a=1; b=2"
                        for part in raw.split(';'):
                            part = part.strip()
                            if not part or '=' not in part:
                                continue
                            name, val = part.split('=', 1)
                            cookies[name.strip()] = unquote(val.strip())
                        break
                # attach parsed cookies for consumers and logs
                scope['cookies'] = cookies
                logger.info("ASGI parsed cookies: %s", {k: (v[:6] + '...') if len(v) > 6 else v for k, v in cookies.items()})

            # 2) If scope['user'] is missing or anonymous, attempt to find user from sessionid
            user_in_scope = scope.get('user')
            if not user_in_scope or not getattr(user_in_scope, 'is_authenticated', False):
                session_key = cookies.get('sessionid') or None
                if session_key:
                    user, dbg = await _user_from_session_key(session_key)
                    if user:
                        scope['user'] = user
                        logger.info("ASGI restored user from session: %s (session=%s)", getattr(user, 'id', None), session_key[:8] + '...')
                    else:
                        # explicit message for debugging
                        logger.info("ASGI user restore failed from sessionkey=%s: %s", session_key[:8] + '...', dbg)
                        scope['user'] = AnonymousUser()
                else:
                    logger.info("ASGI no sessionid cookie in scope['cookies']; cannot restore user")
                    scope['user'] = AnonymousUser()
            else:
                # already authenticated (AuthMiddlewareStack maybe populated it)
                logger.info("ASGI scope already has authenticated user id=%s", getattr(scope.get('user'), 'id', None))

        # call inner application
        return await self.inner(scope, receive, send)


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": RobustCookieAuthMiddleware(
        AuthMiddlewareStack(
            URLRouter(main.routing.websocket_urlpatterns)
        )
    ),
})
