import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

# Import your project's websocket routing from the MAIN app
# Change `main.routing` if your routing file is at a different module.
import main.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medwheels.settings')

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter(
        main.routing.websocket_urlpatterns
    ),
})
