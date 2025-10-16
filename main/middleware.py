import json
from urllib.parse import unquote
from django.contrib.sessions.models import Session
from django.contrib.auth import get_user_model
from django.db import close_old_connections

User = get_user_model()

class CookieAuthMiddleware:
    """
    Custom middleware to restore request.session and user
    when standard AuthMiddlewareStack doesn't populate them
    (e.g. Render/Cloudflare stripping cookies).
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        try:
            headers = dict(scope.get("headers") or [])
            cookie_header = headers.get(b"cookie", b"").decode("utf-8")
            cookies = {}
            for c in cookie_header.split(";"):
                if "=" in c:
                    k, v = c.split("=", 1)
                    cookies[k.strip()] = unquote(v.strip())

            session_key = cookies.get("sessionid")
            if session_key:
                session = Session.objects.get(session_key=session_key)
                data = session.get_decoded()
                user_id = data.get("_auth_user_id")
                if user_id:
                    user = User.objects.filter(id=user_id).first()
                    if user:
                        scope["user"] = user
                        scope["session"] = session
                        close_old_connections()
        except Exception as e:
            # failsafe — don’t crash
            import logging
            logging.getLogger("django.channels").warning(f"CookieAuthMiddleware error: {e}")

        return await self.inner(scope, receive, send)
