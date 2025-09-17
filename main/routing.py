
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # driver live (optional: specific driver watch UI)
    re_path(r'ws/driver_live/(?P<driver_id>\d+)/$', consumers.DriverLiveConsumer.as_asgi()),

    # driver dashboard socket: drivers listen here for incoming ride requests
    re_path(r'ws/driver/(?P<driver_id>\d+)/$', consumers.DriverConsumer.as_asgi()),

    # rider tracking socket: the find_driver.html connects here for a particular ride
    re_path(r'ws/ride/(?P<ride_id>\d+)/$', consumers.RideConsumer.as_asgi()),
]
