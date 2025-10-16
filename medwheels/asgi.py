import os
import logging
from urllib.parse import unquote

# Ensure Django settings are loaded before importing ORM models
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medwheels.settings')

import django
django.setup()  # MUST be called before importing Django ORM classes

from django.core.asgi import get_asgi_application
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.models import Session

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

import main.routing

# Import your custom Users model (used by your code)
# adjust path if your app module is named differently
from verify.models import Users as CustomUsers

logger = logging.getLogger("medwheels.asgi")
logger.setLevel(logging.INFO)

django_asgi_app = get_asgi_application()
DjangoUser = get_user_model()


# sync DB work wrapped for async
@sync_to_async
def _resolve_user_from_session(session_key):
    """
    Returns (user_obj_or_None, debug_message)
    This tries:
      1) Django auth key: '_auth_user_id' -> resolve via DjangoUser
      2) Custom 'user_id' -> resolve via verify.models.Users
    """
    try:
        sess = Session.objects.get(session_key=session_key)
    except Session.DoesNotExist:
        return None, f"session not found for key {session_key!r}"

    try:
        data = sess.get_decoded()
    except Exception as e:
        return None, f"session decode failed: {e}"

    # 1) Try Django auth user
    auth_uid = data.get('_auth_user_id')
    if auth_uid:
        try:
            u = DjangoUser.objects.get(pk=auth_uid)
            return u, f"_auth_user_id -> DjangoUser id={auth_uid}"
        except DjangoUser.DoesNotExist:
            return None, f"_auth_user_id {auth_uid} not found in DjangoUser"

    # 2) Try custom session key 'user_id' used by your codebase
    custom_uid = data.get('user_id')
    if custom_uid:
        try:
            # custom user id may be stored as int or str; coerce
            u = CustomUsers.objects.get(pk=int(custom_uid))
            return u, f"user_id -> CustomUsers id={custom_uid}"
        except CustomUsers.DoesNotExist:
            return None, f"user_id {custom_uid} not found in CustomUsers"
        except Exception as e:
            return None, f"user_id lookup failed: {e}"

    # no recognizable auth info
    return None, "session contains no '_auth_user_id' or 'user_id'"


class RobustCookieAuthMiddleware:
    """
    WebSocket middleware that:
      - ensures scope['cookies'] is present (parses cookie header if needed)
      - resolves the user from session key checking both Django auth (_auth_user_id)
        and the custom 'user_id' session key (verify.models.Users)
      - sets scope['user'] to the resolved user instance (or AnonymousUser)
      - logs diagnostic messages for debugging
    Wrap AuthMiddlewareStack with this middleware in application below.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'websocket':
            # Ensure cookies exist in scope (Channels sometimes leaves it empty)
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
                        for part in raw.split(';'):
                            part = part.strip()
                            if not part or '=' not in part:
                                continue
                            name, val = part.split('=', 1)
                            cookies[name.strip()] = unquote(val.strip())
                        break
                scope['cookies'] = cookies
                logger.info("ASGI parsed cookies: %s", {k: (v[:10] + '...') if len(v) > 10 else v for k, v in cookies.items()})

            # If user not authenticated in scope, try restore from sessionid
            user_in_scope = scope.get('user')
            if not user_in_scope or not getattr(user_in_scope, 'is_authenticated', False):
                session_key = scope.get('cookies', {}).get('sessionid')
                if session_key:
                    user_obj, dbg = await _resolve_user_from_session(session_key)
                    if user_obj:
                        scope['user'] = user_obj
                        # Log which model we restored from (DjangoUser or CustomUsers)
                        model_name = type(user_obj).__name__
                        logger.info("ASGI restored user from session: %s (model=%s) session=%s", getattr(user_obj, 'id', None), model_name, (session_key[:8] + '...'))
                    else:
                        logger.info("ASGI user restore failed from sessionkey=%s: %s", (session_key[:8] + '...'), dbg)
                        scope['user'] = AnonymousUser()
                else:
                    logger.info("ASGI no sessionid cookie found in scope['cookies']")
                    scope['user'] = AnonymousUser()
            else:
                logger.info("ASGI scope already has authenticated user id=%s", getattr(scope.get('user'), 'id', None))

        return await self.inner(scope, receive, send)


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": RobustCookieAuthMiddleware(
        AuthMiddlewareStack(
            URLRouter(main.routing.websocket_urlpatterns)
        )
    ),
})
