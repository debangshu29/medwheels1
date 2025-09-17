
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class DriverLiveConsumer(AsyncWebsocketConsumer):
    """
    For pages that want to receive live updates about a specific driver.
    Connect to: ws://.../ws/driver_live/<driver_id>/
    The server will group_send to 'driver_<id>' with types like 'location.update' and 'ride.request'.
    """
    async def connect(self):
        self.driver_id = self.scope['url_route']['kwargs']['driver_id']
        self.group_name = f"driver_{self.driver_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Handler for 'location.update' -> location_update
    async def location_update(self, event):
        await self.send_json({
            'type': 'location.update',
            'driver_id': event.get('driver_id'),
            'lat': event.get('lat'),
            'lng': event.get('lng'),
            'is_online': event.get('is_online', True),
            'last_seen': event.get('last_seen'),
        })

    # Handler for 'ride.request' -> ride_request
    async def ride_request(self, event):
        await self.send_json({
            'type': 'ride.request',
            'ride_id': event.get('ride_id'),
            'pickup': event.get('pickup'),
            'pickup_lat': event.get('pickup_lat'),
            'pickup_lng': event.get('pickup_lng'),
            'dropoff': event.get('dropoff'),
            'ambulance_type': event.get('ambulance_type'),
            'distance_m': event.get('distance_m'),
            'requested_at': event.get('requested_at'),
        })

    async def receive(self, text_data=None, bytes_data=None):
        # Not used at the moment; kept for future extension.
        return

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload))


class RideConsumer(AsyncWebsocketConsumer):
    """
    WebSocket for the rider tracking page.
    Connect to: ws://.../ws/ride/<ride_id>/
    Receives: ride.assigned, location.update, ride.cancelled, ride.matching_failed
    """
    async def connect(self):
        self.ride_id = self.scope['url_route']['kwargs']['ride_id']
        self.group_name = f"ride_{self.ride_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def ride_assigned(self, event):
        # event should include 'driver' dict and optionally lat/lng/eta_min/fare
        await self.send_json({
            'type': 'ride.assigned',
            'driver': event.get('driver'),
            'lat': event.get('lat'),
            'lng': event.get('lng'),
            'eta_min': event.get('eta_min'),
            'fare': event.get('fare'),
        })

    async def location_update(self, event):
        await self.send_json({
            'type': 'location.update',
            'driver_id': event.get('driver_id'),
            'lat': event.get('lat'),
            'lng': event.get('lng'),
            'last_seen': event.get('last_seen')
        })

    async def ride_cancelled(self, event):
        await self.send_json({'type': 'ride.cancelled', 'ride_id': event.get('ride_id')})

    async def ride_matching_failed(self, event):
        await self.send_json({'type': 'ride.matching_failed'})

    async def receive(self, text_data=None, bytes_data=None):
        # Rider client does not send messages (for now). Future: chat, ack events, etc.
        return

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload))


class DriverConsumer(AsyncWebsocketConsumer):
    """
    WebSocket for driver dashboard that receives ride requests and location updates.
    Connect to: ws://.../ws/driver/<driver_id>/
    """
    async def connect(self):
        self.driver_id = self.scope['url_route']['kwargs']['driver_id']
        self.group_name = f"driver_{self.driver_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def ride_request(self, event):
        await self.send_json({'type': 'ride.request', 'data': event})

    async def location_update(self, event):
        await self.send_json({'type': 'location.update', 'data': event})

    async def driver_assignment_confirmed(self, event):
        await self.send_json({'type': 'driver.assignment_confirmed', 'ride_id': event.get('ride_id')})

    async def receive(self, text_data=None, bytes_data=None):
        # If drivers will send WS messages (e.g., "accept via socket"), handle that here.
        return

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload))
