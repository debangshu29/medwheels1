from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
import json
import random
from decimal import Decimal
from math import radians, cos, sin, asin, sqrt
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import Http404
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.views.decorators.csrf import ensure_csrf_cookie
from verify.models import Users, Drivers,DriverDocuments
from .models import DriverLive, DriverLocation, Ride
from django.urls import reverse
from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required, user_passes_test




DEFAULT_MAP_CENTER = (22.5726, 88.3639)  # fallback (Kolkata) - change to your city
def debug_channel_layer(request):
    try:
        from channels.layers import get_channel_layer
        cl = get_channel_layer()
        return JsonResponse({'ok': True, 'layer': str(type(cl)), 'repr': repr(cl)})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})

# helpers
def haversine_m(lat1, lon1, lat2, lon2):
    """Return distance in meters between two (lat,lng)."""
    # convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    R = 6371000  # Earth radius in meters
    return R * c
def service_view(request):
    """
    Renders the service page. Pass GOOGLE_MAPS_API_KEY and DEFAULT_MAP_CENTER in context.
    """
    google_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', 'YOUR_GOOGLE_API_KEY')
    return render(request, 'service.html', {
        'GOOGLE_MAPS_API_KEY': google_key,
        'DEFAULT_MAP_CENTER': DEFAULT_MAP_CENTER,
    })


def service_estimate(request):
    """
    Placeholder for next step - route, estimate, price.
    For now show a minimal page reading session's ride_search.
    """
    ride = request.session.get('ride_search')
    if not ride:
        return redirect(reverse('service'))

    return render(request, 'service_estimate.html', {'ride': ride})

@require_GET
def api_nearby_ambulances(request):
    """
    Returns JSON list of nearby ambulances given lat & lng query params.
    For now we mock several ambulances around the provided coordinate.
    Later: replace with real DB query using Drivers / live locations.
    """
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')
    try:
        if lat is None or lng is None:
            raise ValueError("lat/lng required")
        lat = float(lat); lng = float(lng)
    except Exception:
        return HttpResponseBadRequest(json.dumps({'error': 'Provide lat & lng as query params'}), content_type='application/json')

    # mock ambulances: generate small offsets around the location
    ambulances = []
    for i in range(8):
        # jitter up to ~0.003 degrees (~300m)
        jitter_lat = (random.random() - 0.5) * 0.006
        jitter_lng = (random.random() - 0.5) * 0.006
        ambulances.append({
            'id': f'AMB-{int(timezone.now().timestamp())}-{i}',
            'lat': lat + jitter_lat,
            'lng': lng + jitter_lng,
            'heading': int(random.random() * 360),
            'status': random.choice(['idle', 'on_trip', 'busy']),
            'vehicle': random.choice(['BLS', 'ALS', 'ICU']),
        })

    return JsonResponse({'ambulances': ambulances})


@require_POST
def api_see_price(request):
    """
    Accepts JSON POST with pickup/drop addresses + coords.
    For now: validate and store in session, return next_url (estimation page).
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest(json.dumps({'ok': False, 'error': 'invalid json'}), content_type='application/json')

    pickup = payload.get('pickup')  # dict: {address, lat, lng}
    dropoff = payload.get('dropoff')  # same
    if not pickup or not pickup.get('lat') or not pickup.get('lng'):
        return JsonResponse({'ok': False, 'error': 'pickup coordinates required'}, status=400)

    # Save search into session to be used on estimate page
    request.session['ride_search'] = {
        'pickup': pickup,
        'dropoff': dropoff,
        'created_at': timezone.now().isoformat()
    }
    # Next page (to implement later)
    next_url = reverse('service_estimate')
    return JsonResponse({'ok': True, 'next_url': next_url})

def _get_driver_for_session(request):
    """
    Return Drivers instance for currently-authenticated driver based on session user_id.
    Returns (driver_obj, None) or (None, error_response) so callers can return early.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        return None, HttpResponseForbidden(json.dumps({'ok': False, 'error': 'not authenticated'}), content_type='application/json')
    try:
        user = Users.objects.get(pk=user_id)
    except Users.DoesNotExist:
        return None, HttpResponseForbidden(json.dumps({'ok': False, 'error': 'user not found'}), content_type='application/json')

    driver = Drivers.objects.filter(user=user).first()
    if not driver:
        return None, HttpResponseForbidden(json.dumps({'ok': False, 'error': 'driver profile not found'}), content_type='application/json')
    return driver, None

@ensure_csrf_cookie
def driver_dashboard(request):
    """
    Render driver dashboard page. Session must contain user_id for mapping.
    Provide driver profile to template.
    """
    # Map session user => custom Users => Drivers profile
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('signup_login')  # or your driver login URL

    try:
        user = Users.objects.get(pk=user_id)
    except Users.DoesNotExist:
        request.session.flush()
        return redirect('signup_login')

    driver = Drivers.objects.filter(user=user).first()
    if not driver:
        # not a driver; redirect or show error
        return render(request, 'driver_dashboard.html', {'error': 'Driver profile not found. Please complete your application.'})

    # Optionally provide live info for map / current status
    live = None
    if hasattr(driver, 'live'):
        live = {
            'lat': float(driver.live.latitude) if driver.live.latitude is not None else None,
            'lng': float(driver.live.longitude) if driver.live.longitude is not None else None,
            'is_online': driver.live.is_online,
            'last_seen': driver.live.last_seen.isoformat() if driver.live.last_seen else None
        }

    context = {
        'driver': driver,
        'user': user,
        'live': live,
    }
    return render(request, 'driver_dashboard.html', context)


@require_POST
def api_driver_live_update(request):
    """
    Receive JSON { lat: <float>, lng: <float>, is_online: true/false } from driver dashboard.
    Updates/creates DriverLive and appends DriverLocation.
    Also broadcasts a group message to WebSocket clients subscribed to group "driver_<id>".
    """
    # find driver for session
    driver, auth_err = _get_driver_for_session(request)
    if auth_err:
        return auth_err

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest(
            json.dumps({'ok': False, 'error': 'invalid json'}),
            content_type='application/json'
        )

    lat = payload.get('lat')
    lng = payload.get('lng')
    is_online = payload.get('is_online', True)

    if lat is None or lng is None:
        return HttpResponseBadRequest(
            json.dumps({'ok': False, 'error': 'lat and lng required'}),
            content_type='application/json'
        )

    # coercion and validation
    try:
        lat = Decimal(str(lat))
        lng = Decimal(str(lng))
    except Exception:
        return HttpResponseBadRequest(
            json.dumps({'ok': False, 'error': 'invalid lat/lng'}),
            content_type='application/json'
        )

    now = timezone.now()

    # update or create DriverLive row
    live_obj, created = DriverLive.objects.update_or_create(
        driver=driver,
        defaults={'latitude': lat, 'longitude': lng, 'is_online': bool(is_online), 'last_seen': now}
    )

    # append telemetry (DriverLocation) - keep as append-only
    try:
        DriverLocation.objects.create(
            driver=driver,
            latitude=lat,
            longitude=lng,
            recorded_at=now
        )
    except Exception:
        # If this fails for any reason, we still want to return success for live update.
        # Log in real app.
        pass

    # --- BROADCAST to WebSocket group (so any user subscribed to this driver's group gets the update) ---
    # existing broadcast to driver_{id}
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"driver_{driver.id}",
            {
                'type': 'location.update',
                'driver_id': driver.id,
                'lat': float(lat),
                'lng': float(lng),
                'is_online': bool(is_online),
                'last_seen': now.isoformat()
            }
        )
        # Also notify any rider(s) with assigned rides to this driver
        # Find rides with status where the rider should be tracking: assigned / accepted / on_trip
        assigned_rides = Ride.objects.filter(driver=driver,
                                             status__in=['assigned', 'accepted', 'on_trip'])  # adapt statuses you use
        for r in assigned_rides:
            async_to_sync(channel_layer.group_send)(
                f"ride_{r.id}",
                {
                    'type': 'location.update',
                    'driver_id': driver.id,
                    'lat': float(lat),
                    'lng': float(lng),
                    'last_seen': now.isoformat()
                }
            )
    except Exception:
        pass

    return JsonResponse({'ok': True, 'last_seen': now.isoformat()})


@require_GET
def api_nearby_ambulances(request):
    """
    Return nearby *real* ambulances (DriverLive rows with is_online=True).
    Query params:
      - lat (required)
      - lng (required)
      - radius_m (optional, default 5000 meters)
      - max_results (optional, default 20)

    Returns JSON: { ambulances: [ { id, driver_id, full_name, lat, lng, distance_m, heading, status, vehicle, photo_url, last_seen } ] }
    """
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')
    radius_m = float(request.GET.get('radius_m') or 5000.0)
    max_results = int(request.GET.get('max_results') or 20)

    try:
        if lat is None or lng is None:
            raise ValueError("lat/lng required")
        plat = float(lat); plng = float(lng)
    except Exception:
        return HttpResponseBadRequest(
            json.dumps({'error': 'Provide lat & lng as query params (floats).'}),
            content_type='application/json'
        )

    # quick bbox filter to avoid full table scan: approximate degrees for radius
    # 1 deg lat ≈ 111320 meters
    try:
        deg_lat = radius_m / 111320.0
        # longitude degrees scale by cos(latitude)
        deg_lng = radius_m / (111320.0 * max(0.000001, abs(cos(radians(plat)))))
    except Exception:
        deg_lat = radius_m / 111320.0
        deg_lng = radius_m / 111320.0

    min_lat = plat - deg_lat
    max_lat = plat + deg_lat
    min_lng = plng - deg_lng
    max_lng = plng + deg_lng

    q = DriverLive.objects.filter(
        is_online=True,
        latitude__isnull=False,
        longitude__isnull=False,
        latitude__gte=min_lat, latitude__lte=max_lat,
        longitude__gte=min_lng, longitude__lte=max_lng
    ).select_related('driver')[:500]  # safety cap

    ambulances = []
    for live in q:
        try:
            d_m = haversine_m(plat, plng, float(live.latitude), float(live.longitude))
        except Exception:
            continue
        if d_m > radius_m:
            continue

        driver = live.driver
        # try to pick a photo
        doc = DriverDocuments.objects.filter(driver=driver).order_by('-uploaded_at').first()
        photo_url = ''
        if doc and getattr(doc, 'photo', None) and hasattr(doc.photo, 'url'):
            photo_url = request.build_absolute_uri(doc.photo.url)
        else:
            if getattr(driver.user, 'profile_picture', None):
                photo_url = driver.user.profile_picture

        ambulances.append({
            'id': f'driverlive-{live.id}',
            'driver_id': driver.id,
            'full_name': getattr(driver, 'full_name', '') or getattr(driver.user, 'get_full_name', '') or str(driver.id),
            'lat': float(live.latitude),
            'lng': float(live.longitude),
            'distance_m': int(d_m),
            'heading': getattr(live, 'heading', None) or 0,
            'status': getattr(live, 'is_online', True) and getattr(driver, 'status', '') or 'offline',
            'vehicle': getattr(driver, 'vehicle_type', '') or '',
            'photo_url': photo_url,
            'last_seen': live.last_seen.isoformat() if getattr(live, 'last_seen', None) else None,
        })

    # sort by distance and trim
    ambulances.sort(key=lambda x: x['distance_m'])
    ambulances = ambulances[:max_results]

    return JsonResponse({'ambulances': ambulances})


@require_POST
def api_estimate(request):
    """
    Accepts { pickup: {lat,lng,address}, dropoff: {..} }
    Returns candidates: list of nearby drivers with simple ETA/distance/fare.
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest(json.dumps({'ok': False, 'error': 'invalid json'}), content_type='application/json')

    pickup = payload.get('pickup') or {}
    dropoff = payload.get('dropoff') or None
    try:
        plat = float(pickup.get('lat'))
        plng = float(pickup.get('lng'))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'pickup lat/lng required'}, status=400)

    # configuration
    MAX_RESULTS = 6
    AVG_SPEED_KMPH = 25.0  # conservative city speed for ETA estimate
    BASE_FARE = Decimal(getattr(settings, 'FARE_BASE', '200.00'))  # rupee base
    PER_KM = Decimal(getattr(settings, 'FARE_PER_KM', '10.0'))
    PER_MIN = Decimal(getattr(settings, 'FARE_PER_MIN', '2.0'))

    # query DriverLive for online drivers and compute distances
    q = DriverLive.objects.filter(is_online=True).select_related('driver')[:200]  # limit scan
    candidates = []
    for live in q:
        if live.latitude is None or live.longitude is None:
            continue
        try:
            d_m = haversine_m(plat, plng, float(live.latitude), float(live.longitude))
        except Exception:
            continue
        d_km = Decimal(d_m) / Decimal(1000)
        eta_min = (d_km / Decimal(AVG_SPEED_KMPH)) * Decimal(60)
        # simple fare estimate: base + per_km*distance + per_min*eta
        fare = (BASE_FARE + (PER_KM * d_km) + (PER_MIN * eta_min)).quantize(Decimal('0.01'))
        driver = live.driver
        # fetch driver photo (from DriverDocuments.photo) or driver.user.profile_picture
        doc = DriverDocuments.objects.filter(driver=driver).order_by('-uploaded_at').first()
        photo_url = ''
        if doc and getattr(doc, 'photo', None) and hasattr(doc.photo, 'url'):
            photo_url = request.build_absolute_uri(doc.photo.url)
        else:
            if getattr(driver.user, 'profile_picture', None):
                photo_url = driver.user.profile_picture
        candidates.append({
            'driver_id': driver.id,
            'full_name': driver.full_name,
            'vehicle': getattr(doc, 'vehicle', '') or '',
            'lat': float(live.latitude),
            'lng': float(live.longitude),
            'distance_m': int(d_m),
            'eta_s': int((eta_min * Decimal(60)).quantize(Decimal('1'))),  # seconds
            'eta_min': int(eta_min.quantize(Decimal('1'))),
            'fare': str(fare),
            'photo_url': photo_url,
            'status': driver.status,
        })

    # sort by ETA / distance and return top N
    candidates.sort(key=lambda x: (x['eta_s'], x['distance_m']))
    top = candidates[:MAX_RESULTS]
    return JsonResponse({'ok': True, 'candidates': top})

@login_required
@require_POST
def api_book_ride(request):
    """
    Book a ride with a selected driver id.
    POST body: { driver_id: int, pickup: {...}, dropoff: {...} }
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest(json.dumps({'ok': False, 'error': 'invalid json'}), content_type='application/json')

    driver_id = payload.get('driver_id')
    pickup = payload.get('pickup') or {}
    dropoff = payload.get('dropoff') or {}

    if not driver_id:
        return JsonResponse({'ok': False, 'error': 'driver_id required'}, status=400)
    try:
        driver = Drivers.objects.get(pk=int(driver_id))
    except Drivers.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'driver not found'}, status=404)

    # basic user resolution using session
    user_id = request.session.get('user_id')
    if not user_id:
        return HttpResponseForbidden(json.dumps({'ok': False, 'error': 'authentication required'}), content_type='application/json')
    try:
        user = Users.objects.get(pk=user_id)
    except Users.DoesNotExist:
        return HttpResponseForbidden(json.dumps({'ok': False, 'error': 'user missing'}), content_type='application/json')

    # create Ride snapshot
    ride = Ride.objects.create(
        user=user,
        driver=driver,
        pickup_address=pickup.get('address') or '',
        pickup_lat=pickup.get('lat'),
        pickup_lng=pickup.get('lng'),
        dropoff_address=dropoff.get('address') if dropoff else '',
        dropoff_lat=dropoff.get('lat') if dropoff else None,
        dropoff_lng=dropoff.get('lng') if dropoff else None,
        status='requested',
    )

    # notify driver via channels
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"driver_{driver.id}",
            {
                'type': 'ride.request',     # consumer handler
                'ride_id': ride.id,
                'pickup': ride.pickup_address,
                'pickup_lat': float(ride.pickup_lat),
                'pickup_lng': float(ride.pickup_lng),
                'dropoff': ride.dropoff_address,
            }
        )
    except Exception:
        # non-fatal
        pass

    return JsonResponse({'ok': True, 'ride_id': ride.id})

@require_POST
def api_request_ambulance_type(request):
    """
    POST JSON:
      { ambulance_type: 'medwheels_basic',
        pickup: { address, lat, lng },
        dropoff: { address, lat, lng } (optional) }

    Creates a Ride (driver=NULL) and notifies top N nearby online drivers (by distance).
    Returns: { ok: True, ride_id: <id>, notified: <n> }
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest(json.dumps({'ok': False, 'error': 'invalid json'}), content_type='application/json')

    ambulance_type = payload.get('ambulance_type') or 'medwheels_basic'
    pickup = payload.get('pickup') or {}
    dropoff = payload.get('dropoff') or None

    # validate pickup coords
    try:
        plat = float(pickup.get('lat'))
        plng = float(pickup.get('lng'))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'pickup lat/lng required'}, status=400)

    # require authenticated user via session (your code uses session['user_id'])
    user_id = request.session.get('user_id')
    if not user_id:
        return HttpResponseForbidden(json.dumps({'ok': False, 'error': 'authentication required'}), content_type='application/json')
    try:
        user = Users.objects.get(pk=user_id)
    except Users.DoesNotExist:
        return HttpResponseForbidden(json.dumps({'ok': False, 'error': 'user missing'}), content_type='application/json')

    # Create Ride row with driver=NULL (this is allowed in your model)
    # Use transaction so ride exists before notifications
    ride = None
    try:
        with transaction.atomic():
            ride = Ride.objects.create(
                user=user,
                driver=None,
                pickup_address=pickup.get('address') or '',
                pickup_lat=plat,
                pickup_lng=plng,
                dropoff_address=dropoff.get('address') if dropoff else '',
                dropoff_lat=float(dropoff.get('lat')) if dropoff and dropoff.get('lat') is not None else None,
                dropoff_lng=float(dropoff.get('lng')) if dropoff and dropoff.get('lng') is not None else None,
                status='matching',  # indicates matching in progress
            )
    except Exception as e:
        # If creating Ride fails, still return a meaningful error
        return JsonResponse({'ok': False, 'error': 'could not create ride', 'detail': str(e)}, status=500)

    # Find nearby online drivers (DriverLive). We'll compute distances and sort.
    # Tune these parameters to fit your needs:
    MAX_SEARCH = 200
    NOTIFY_TOP_N = 8
    SEARCH_RADIUS_M = 10000.0  # 10km max (you can tune)

    # Bounding box to reduce DB scan (approx)
    try:
        deg_lat = SEARCH_RADIUS_M / 111320.0
        deg_lng = SEARCH_RADIUS_M / (111320.0 * max(0.000001, abs(cos(radians(plat)))))
    except Exception:
        deg_lat = SEARCH_RADIUS_M / 111320.0
        deg_lng = SEARCH_RADIUS_M / 111320.0

    min_lat = plat - deg_lat
    max_lat = plat + deg_lat
    min_lng = plng - deg_lng
    max_lng = plng + deg_lng

    q = DriverLive.objects.filter(
        is_online=True,
        latitude__isnull=False,
        longitude__isnull=False,
        latitude__gte=min_lat, latitude__lte=max_lat,
        longitude__gte=min_lng, longitude__lte=max_lng
    ).select_related('driver')[:MAX_SEARCH]

    # compute distances
    nearby = []
    for live in q:
        try:
            d_m = haversine_m(plat, plng, float(live.latitude), float(live.longitude))
        except Exception:
            continue
        if d_m > SEARCH_RADIUS_M:
            continue
        nearby.append((d_m, live))

    # sort by distance asc
    nearby.sort(key=lambda x: x[0])

    # notify top N drivers via channels (group_send to "driver_<id>")
    channel_layer = get_channel_layer()
    notified = 0
    for d_m, live in nearby[:NOTIFY_TOP_N]:
        try:
            async_to_sync(channel_layer.group_send)(
                f"driver_{live.driver.id}",
                {
                    'type': 'ride.request',     # your driver consumer must handle this
                    'ride_id': ride.id,
                    'pickup': ride.pickup_address,
                    'pickup_lat': float(ride.pickup_lat),
                    'pickup_lng': float(ride.pickup_lng),
                    'dropoff': ride.dropoff_address,
                    'ambulance_type': ambulance_type,
                    'distance_m': float(d_m),
                    'requested_at': ride.requested_at.isoformat() if getattr(ride, 'requested_at', None) else timezone.now().isoformat(),
                }
            )
            notified += 1
        except Exception:
            # ignore send errors per driver but continue
            continue

    tracking_url = reverse('find_driver', args=[ride.id])
    return JsonResponse({'ok': True, 'ride_id': ride.id, 'notified': notified, 'tracking_url': tracking_url})

def find_driver_view(request, ride_id):
    """
    Render the find_driver.html page for a rider to watch matching/assignment.
    Ensures the current session user owns the ride (simple safety).
    The template will receive:
       - GOOGLE_MAPS_API_KEY
       - DEFAULT_MAP_CENTER
       - ride_json -> JSON blob with ride_id, pickup, drop, fare
    """
    google_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', 'YOUR_GOOGLE_API_KEY')

    try:
        ride = Ride.objects.get(pk=ride_id)
    except Ride.DoesNotExist:
        raise Http404("Ride not found")

    # Basic ownership check: your app uses session['user_id']
    user_id = request.session.get('user_id')
    if not user_id or ride.user_id != int(user_id):
        # Option: allow viewing if you prefer; for privacy we require owner.
        return HttpResponseForbidden("Permission denied")

    # Build ride JSON for the template (only necessary fields)
    # Use estimated_fare or final_fare if present
    fare_val = None
    if getattr(ride, 'estimated_fare', None) is not None:
        fare_val = float(ride.estimated_fare)
    elif getattr(ride, 'final_fare', None) is not None:
        fare_val = float(ride.final_fare)

    ride_payload = {
        'ride_id': ride.id,
        'pickup': {
            'lat': float(ride.pickup_lat) if ride.pickup_lat is not None else None,
            'lng': float(ride.pickup_lng) if ride.pickup_lng is not None else None,
            'address': ride.pickup_address or ''
        },
        # intentionally named "drop" to match template JS
        'drop': None,
        'fare': fare_val,
        'status': ride.status
    }
    if ride.dropoff_lat is not None and ride.dropoff_lng is not None:
        ride_payload['drop'] = {
            'lat': float(ride.dropoff_lat),
            'lng': float(ride.dropoff_lng),
            'address': ride.dropoff_address or ''
        }

    return render(request, 'find_driver.html', {
        'GOOGLE_MAPS_API_KEY': google_key,
        'DEFAULT_MAP_CENTER': DEFAULT_MAP_CENTER,
        'ride_json': json.dumps(ride_payload)
    })



@require_POST
def api_driver_respond(request):
    """
    Driver responds to a ride request (accept or reject).
    POST JSON: { ride_id: <int>, action: 'accept'|'reject' }
    Authentication: driver must be logged-in in session (use _get_driver_for_session)
    Returns JSON: { ok: True, assigned: True/False, message: ... }
    """
    driver, auth_err = _get_driver_for_session(request)
    if auth_err:
        return auth_err

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest(json.dumps({'ok': False, 'error': 'invalid json'}), content_type='application/json')

    ride_id = payload.get('ride_id')
    action = payload.get('action')

    if not ride_id or action not in ('accept', 'reject'):
        return HttpResponseBadRequest(json.dumps({'ok': False, 'error': 'ride_id and action required'}), content_type='application/json')

    try:
        ride_id = int(ride_id)
    except Exception:
        return HttpResponseBadRequest(json.dumps({'ok': False, 'error': 'invalid ride_id'}), content_type='application/json')

    if action == 'reject':
        # Optionally record rejection (not implemented here). Just return ok.
        return JsonResponse({'ok': True, 'rejected': True})

    # action == 'accept' -> attempt atomic assignment
    try:
        with transaction.atomic():
            # Lock the ride row
            ride = Ride.objects.select_for_update().get(pk=ride_id)

            # validation checks
            if ride.driver_id is not None:
                # already assigned
                return JsonResponse({'ok': False, 'assigned': False, 'error': 'already assigned'})

            if ride.status not in ('matching', 'requested'):
                return JsonResponse({'ok': False, 'assigned': False, 'error': f'invalid ride status: {ride.status}'})

            # Everything ok -> assign
            ride.driver = driver
            ride.status = 'assigned'
            ride.assigned_at = timezone.now() if hasattr(ride, 'assigned_at') else timezone.now()
            ride.save()

            # Prepare driver payload for broadcast to rider
            driver_payload = {
                'id': driver.id,
                'name': getattr(driver, 'full_name', '') or str(driver.id),
                'phone': getattr(driver.user, 'phone', '') or '',
                'vehicle_no': getattr(driver, 'vehicle_no', '') or getattr(driver, 'vehicle_number', '') or '',
                'vehicle_type': getattr(driver, 'vehicle_type', '') or '',
                'photo_url': None
            }
            # Try to fill photo_url
            doc = DriverDocuments.objects.filter(driver=driver).order_by('-uploaded_at').first()
            if doc and getattr(doc, 'photo', None) and hasattr(doc.photo, 'url'):
                driver_payload['photo_url'] = request.build_absolute_uri(doc.photo.url)
            else:
                # fallback to user profile pic if any
                if getattr(driver.user, 'profile_picture', None):
                    driver_payload['photo_url'] = driver.user.profile_picture

            # Send a message to the rider's websocket group (ride_{ride.id})
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"ride_{ride.id}",
                {
                    'type': 'ride.assigned',
                    'driver': driver_payload,
                    # include driver's last known location if available
                    'lat': float(driver.live.latitude) if getattr(driver, 'live', None) and driver.live.latitude is not None else None,
                    'lng': float(driver.live.longitude) if getattr(driver, 'live', None) and driver.live.longitude is not None else None,
                    'eta_min': None,  # optionally compute ETA here and add
                    'fare': getattr(ride, 'fare', None),
                }
            )

            # Optionally inform the driver (their websocket) they were assigned for UI.
            async_to_sync(channel_layer.group_send)(
                f"driver_{driver.id}",
                {
                    'type': 'driver.assignment_confirmed',
                    'ride_id': ride.id,
                }
            )

            return JsonResponse({'ok': True, 'assigned': True, 'ride_id': ride.id})
    except Ride.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'ride not found'}, status=404)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'server error', 'detail': str(e)}, status=500)


@require_POST
def api_cancel_ride(request, ride_id):
    """
    Cancel a ride. Rider-initiated cancel.
    POST only.
    """
    # check user owns ride
    user_id = request.session.get('user_id')
    if not user_id:
        return HttpResponseForbidden(json.dumps({'ok': False, 'error': 'auth required'}), content_type='application/json')

    try:
        ride = Ride.objects.get(pk=ride_id)
    except Ride.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'ride not found'}, status=404)

    if ride.user_id != int(user_id):
        return HttpResponseForbidden(json.dumps({'ok': False, 'error': 'not your ride'}), content_type='application/json')

    # change status and broadcast cancel to driver & rider groups
    prev_status = ride.status
    ride.status = 'cancelled'
    ride.cancelled_at = timezone.now() if hasattr(ride, 'cancelled_at') else timezone.now()
    ride.save()

    # notify ride group
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"ride_{ride.id}",
            {'type': 'ride.cancelled', 'ride_id': ride.id}
        )
        # notify driver group if assigned
        if ride.driver_id:
            async_to_sync(channel_layer.group_send)(
                f"driver_{ride.driver_id}",
                {'type': 'ride.cancelled', 'ride_id': ride.id}
            )
    except Exception:
        pass

    return JsonResponse({'ok': True})

