import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

from main.models import Ride
from verify.models import Drivers

logger = logging.getLogger(__name__)
User = get_user_model()


class DriverLiveConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # defensive parsing of driver_id
        try:
            self.driver_id = int(self.scope['url_route']['kwargs'].get('driver_id'))
        except Exception as e:
            logger.warning("DriverLiveConsumer.connect: invalid driver_id: %s; scope=%s", e, self.scope.get('url_route'))
            await self.close(code=4002)
            return
        logger.info("WS handshake scope headers: %s", self.scope.get('headers'))
        logger.info("WS handshake cookies: %s", getattr(self.scope, 'cookies', None))


        user = self.scope.get('user')
        logger.info("DriverLiveConsumer.connect attempt driver_id=%s user_id=%s client=%s",
                    self.driver_id, getattr(user, 'id', None), self.scope.get('client'))

        if not user or not user.is_authenticated:
            logger.info("DriverLiveConsumer.connect: unauthenticated -> close(4001)")
            await self.close(code=4001)
            return

        try:
            driver = await database_sync_to_async(Drivers.objects.get)(pk=self.driver_id)
        except Drivers.DoesNotExist:
            logger.info("DriverLiveConsumer.connect: Drivers.DoesNotExist for id=%s -> close(4002)", self.driver_id)
            await self.close(code=4002)
            return
        except Exception as e:
            logger.exception("DriverLiveConsumer.connect: unexpected error fetching driver %s: %s", self.driver_id, e)
            await self.close(code=4002)
            return

        

        self.group_name = f"driver_{self.driver_id}"
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        except Exception as e:
            logger.exception("DriverLiveConsumer.connect: channel_layer.group_add failed for %s: %s", self.group_name, e)
            await self.close(code=4500)
            return

        logger.info("DriverLiveConsumer.connect: accepted driver_id=%s user_id=%s", self.driver_id, user.id)
        await self.accept()

    async def disconnect(self, close_code):
    # only try to discard if we successfully set self.group_name in connect()
        group = getattr(self, "group_name", None)
        if group:
            try:
                await self.channel_layer.group_discard(group, self.channel_name)
            except Exception as e:
                logger.exception("DriverConsumer.disconnect: error discarding group %s: %s", group, e)
            
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
        try:
            self.driver_id = int(self.scope['url_route']['kwargs'].get('driver_id'))
        except Exception as e:
            logger.warning("DriverConsumer.connect: invalid driver_id: %s; scope=%s", e, self.scope.get('url_route'))
            await self.close(code=4002)
            return
        logger.info("WS handshake scope headers: %s", self.scope.get('headers'))
        logger.info("WS handshake cookies: %s", getattr(self.scope, 'cookies', None))

        user = self.scope.get('user')
        logger.info("DriverConsumer.connect attempt driver_id=%s user_id=%s client=%s",
                    self.driver_id, getattr(user, 'id', None), self.scope.get('client'))

        if not user or not user.is_authenticated:
            logger.info("DriverConsumer.connect: unauthenticated -> close(4001)")
            await self.close(code=4001)
            return

        try:
            driver = await database_sync_to_async(Drivers.objects.get)(pk=self.driver_id)
        except Drivers.DoesNotExist:
            logger.info("DriverConsumer.connect: Drivers.DoesNotExist for id=%s -> close(4002)", self.driver_id)
            await self.close(code=4002)
            return
        except Exception as e:
            logger.exception("DriverConsumer.connect: unexpected error fetching driver %s: %s", self.driver_id, e)
            await self.close(code=4002)
            return

        

        self.group_name = f"driver_{self.driver_id}"
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        except Exception as e:
            logger.exception("DriverConsumer.connect: channel_layer.group_add failed for %s: %s", self.group_name, e)
            await self.close(code=4500)
            return

        logger.info("DriverConsumer.connect: accepted driver_id=%s user_id=%s", self.driver_id, user.id)
        await self.accept()

    async def disconnect(self, close_code):
    # only try to discard if we successfully set self.group_name in connect()
        group = getattr(self, "group_name", None)
        if group:
            try:
                await self.channel_layer.group_discard(group, self.channel_name)
            except Exception as e:
                logger.exception("DriverConsumer.disconnect: error discarding group %s: %s", group, e)
            
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
        try:
            self.ride_id = int(self.scope['url_route']['kwargs'].get('ride_id'))
        except Exception as e:
            logger.warning("RideConsumer.connect: invalid ride_id: %s; scope=%s", e, self.scope.get('url_route'))
            await self.close(code=4002)
            return

        logger.info("WS handshake scope headers: %s", self.scope.get('headers'))
        # show cookie header (raw) for debugging
        cookie_hdr = None
        for k, v in self.scope.get('headers', []):
            if k == b'cookie':
                try:
                    cookie_hdr = v.decode()
                except Exception:
                    cookie_hdr = None
                break
        logger.info("WS handshake cookie header: %s", cookie_hdr)
        logger.info("WS handshake cookies (scope): %s", getattr(self.scope, 'cookies', None))

        # First try the normal middleware-provided user (AuthMiddlewareStack)
        user = self.scope.get('user')
        logger.info("RideConsumer.connect attempt ride_id=%s user_id=%s client=%s",
                    self.ride_id, getattr(user, 'id', None), self.scope.get('client'))

        # If no user provided by middleware, try fallback: parse sessionid from cookie header
        if not user or not getattr(user, 'is_authenticated', False):
            if cookie_hdr:
                try:
                    # parse cookie header manually
                    cookies = {}
                    for part in cookie_hdr.split(';'):
                        if not part:
                            continue
                        if '=' not in part:
                            continue
                        name, val = part.split('=', 1)
                        cookies[name.strip()] = val.strip()

                    session_cookie_name = getattr(settings, 'SESSION_COOKIE_NAME', 'sessionid')
                    session_key = cookies.get(session_cookie_name) or cookies.get('sessionid')

                    if session_key:
                        # load session row and decode to get auth user id
                        try:
                            session_obj = await database_sync_to_async(Session.objects.get)(session_key=session_key)
                            session_data = session_obj.get_decoded()
                            auth_user_id = session_data.get('_auth_user_id') or session_data.get('_auth_user_backend') and session_data.get('_auth_user_id')
                            if auth_user_id:
                                # load User object
                                try:
                                    user_obj = await database_sync_to_async(User.objects.get)(pk=int(auth_user_id))
                                    # attach to scope for downstream checks
                                    self.scope['user'] = user_obj
                                    user = self.scope['user']
                                    logger.info("RideConsumer.connect: fallback session auth succeeded user_id=%s", getattr(user, 'id', None))
                                except Exception as e:
                                    logger.info("RideConsumer.connect: fallback user load failed: %s", e)
                        except Session.DoesNotExist:
                            logger.info("RideConsumer.connect: fallback session not found for key=%s", session_key)
                        except Exception as e:
                            logger.exception("RideConsumer.connect: error loading session during fallback: %s", e)
                except Exception as e:
                    logger.exception("RideConsumer.connect: cookie parse/fallback error: %s", e)

        # final auth check
        user = self.scope.get('user')
        if not user or not getattr(user, 'is_authenticated', False):
            logger.info("RideConsumer.connect: unauthenticated -> close(4001)")
            await self.close(code=4001)
            return

        # load ride and ownership checks (as before)
        try:
            ride = await database_sync_to_async(Ride.objects.get)(pk=self.ride_id)
        except Ride.DoesNotExist:
            logger.info("RideConsumer.connect: Ride.DoesNotExist for id=%s -> close(4002)", self.ride_id)
            await self.close(code=4002)
            return
        except Exception as e:
            logger.exception("RideConsumer.connect: unexpected error fetching ride %s: %s", self.ride_id, e)
            await self.close(code=4002)
            return

        if ride.user_id != user.id:
            logger.info("RideConsumer.connect: ride.user_id (%s) != user.id (%s) -> close(4003)",
                        ride.user_id, user.id)
            await self.close(code=4003)
            return

        self.group_name = f"ride_{self.ride_id}"
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        except Exception as e:
            logger.exception("RideConsumer.connect: channel_layer.group_add failed for %s: %s", self.group_name, e)
            await self.close(code=4500)
            return

        logger.info("RideConsumer.connect: accepted ride_id=%s user_id=%s", self.ride_id, user.id)
        await self.accept()

    async def disconnect(self, close_code):
    # only try to discard if we successfully set self.group_name in connect()
        group = getattr(self, "group_name", None)
        if group:
            try:
                await self.channel_layer.group_discard(group, self.channel_name)
            except Exception as e:
                logger.exception("DriverConsumer.disconnect: error discarding group %s: %s", group, e)
            
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
