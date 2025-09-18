import os

# MUST set the DJANGO_SETTINGS_MODULE before importing Django modules
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medwheels.settings')

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Now safe to import your app routing/consumers
import main.routing

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            main.routing.websocket_urlpatterns
        )
    ),
})
