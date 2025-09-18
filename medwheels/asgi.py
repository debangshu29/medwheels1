import os

# MUST set the DJANGO_SETTINGS_MODULE before anything else that touches Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medwheels.settings')

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Call get_asgi_application() now to run django.setup() so apps are ready
django_asgi_app = get_asgi_application()

# Now it's safe to import your app routing which may import models/consumers
import main.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            main.routing.websocket_urlpatterns
        )
    ),
})
