import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medwheels.settings')

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.sessions import SessionMiddlewareStack   # ✅ add this

django_asgi_app = get_asgi_application()

import main.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    # ✅ wrap AuthMiddlewareStack with SessionMiddlewareStack
    "websocket": SessionMiddlewareStack(
        AuthMiddlewareStack(
            URLRouter(main.routing.websocket_urlpatterns)
        )
    ),
})
