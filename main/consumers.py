# add imports at top of consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from verify.models import Drivers
from main.models import Ride

User = get_user_model()


class DriverLiveConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.driver_id = int(self.scope['url_route']['kwargs']['driver_id'])
        user = self.scope.get('user')
        # Require authenticated user
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return
        # Verify driver belongs to this user
        try:
            driver = await database_sync_to_async(Drivers.objects.get)(pk=self.driver_id)
        except Drivers.DoesNotExist:
            await self.close(code=4002)
            return
        if driver.user_id != user.id:
            await self.close(code=4003)
            return
        self.group_name = f"driver_{self.driver_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def location_update(self, event):
        await self.send_json({
            'type': 'location.update',
            'driver_id': event.get('driver_id'),
            'lat': event.get('lat'),
            'lng': event.get('lng'),
            'is_online': event.get('is_online', True),
            'last_seen': event.get('last_seen'),
        })

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
        return

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload))


class DriverConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.driver_id = int(self.scope['url_route']['kwargs']['driver_id'])
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return
        try:
            driver = await database_sync_to_async(Drivers.objects.get)(pk=self.driver_id)
        except Drivers.DoesNotExist:
            await self.close(code=4002)
            return
        if driver.user_id != user.id:
            await self.close(code=4003)
            return

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
        return

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload))


class RideConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.ride_id = int(self.scope['url_route']['kwargs']['ride_id'])
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return
        # ensure the connecting user is the rider (owner) of this ride
        try:
            ride = await database_sync_to_async(Ride.objects.get)(pk=self.ride_id)
        except Ride.DoesNotExist:
            await self.close(code=4002)
            return
        if ride.user_id != user.id:
            await self.close(code=4003)
            return

        self.group_name = f"ride_{self.ride_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def ride_assigned(self, event):
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
        return

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload))
