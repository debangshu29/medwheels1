
from django.db import models
from django.conf import settings
from decimal import Decimal
import secrets
import hashlib
from datetime import timedelta
from django.utils import timezone

RIDE_STATUS = [
    ('requested','Requested'),
    ('matching','Matching'),
    ('assigned','Assigned'),
    ('accepted','Accepted'),
    ('arrived','Arrived'),
    ('on_trip','On Trip'),
    ('completed','Completed'),
    ('cancelled','Cancelled'),
    ('rejected','Rejected'),
]

PAYMENT_STATUS = [
    ('pending','Pending'),
    ('paid','Paid'),
    ('failed','Failed'),
    ('refunded','Refunded'),
]

class DriverLive(models.Model):
    """
    Single row per driver to store last known location and online status.
    This avoids modifying verify.Drivers while providing fast proximity queries.
    """
    driver = models.OneToOneField('verify.Drivers', on_delete=models.CASCADE, related_name='live')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'driver_live'
        indexes = [
            models.Index(fields=['is_online']),
            models.Index(fields=['-last_seen']),
        ]

class DriverLocation(models.Model):
    """
    Append-only telemetry: keep recent location history for driver tracking.
    Prune older rows with a periodic task to keep table small.
    """
    driver = models.ForeignKey('verify.Drivers', on_delete=models.CASCADE, related_name='locations')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    speed = models.FloatField(blank=True, null=True)
    heading = models.IntegerField(blank=True, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'driver_locations'
        indexes = [
            models.Index(fields=['driver', '-recorded_at']),
            models.Index(fields=['recorded_at']),
        ]

class Ride(models.Model):
    """
    Core booking table. Keep snapshot of pickup/drop addresses + lat/lng.
    """
    user = models.ForeignKey('verify.Users', on_delete=models.CASCADE, related_name='rides',db_constraint=False)
    driver = models.ForeignKey('verify.Drivers', on_delete=models.SET_NULL, null=True, blank=True, related_name='rides', db_constraint=False)

    pickup_address = models.CharField(max_length=500)
    pickup_lat = models.DecimalField(max_digits=9, decimal_places=6)
    pickup_lng = models.DecimalField(max_digits=9, decimal_places=6)

    dropoff_address = models.CharField(max_length=500, blank=True, null=True)
    dropoff_lat = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    dropoff_lng = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)

    requested_at = models.DateTimeField(auto_now_add=True)
    requested_for_at = models.DateTimeField(blank=True, null=True)  # scheduled
    status = models.CharField(max_length=20, choices=RIDE_STATUS, default='requested')

    # minimal estimate fields (we will compute later)
    estimate_distance_m = models.IntegerField(blank=True, null=True)
    estimate_duration_s = models.IntegerField(blank=True, null=True)
    estimated_fare = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    final_fare = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)

    assigned_at = models.DateTimeField(blank=True, null=True)
    accepted_at = models.DateTimeField(blank=True, null=True)
    arrived_at = models.DateTimeField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)

    cancellation_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rides'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['driver', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]

class RideEvent(models.Model):
    """
    Audit trail for rides.
    """
    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name='events')
    actor_user = models.ForeignKey('verify.Users', on_delete=models.SET_NULL, null=True, blank=True)
    actor_type = models.CharField(max_length=30, blank=True, null=True)  # 'user','driver','system','ceo'
    event_type = models.CharField(max_length=80)
    event_data = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ride_events'
        indexes = [models.Index(fields=['ride', '-created_at'])]

class Payment(models.Model):
    ride = models.OneToOneField(Ride, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    provider = models.CharField(max_length=50, blank=True, null=True)
    provider_data = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'payments'
        indexes = [models.Index(fields=['status', 'created_at'])]

class DriverDevice(models.Model):
    """
    Store device tokens for push notifications + optionally auth tokens.
    """
    driver = models.ForeignKey('verify.Drivers', on_delete=models.CASCADE, related_name='devices')
    device_type = models.CharField(max_length=20, choices=[('android','android'),('ios','ios'),('web','web')], default='android')
    push_token = models.CharField(max_length=500)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'driver_devices'
        indexes = [models.Index(fields=['driver']),]

class Review(models.Model):
    ride = models.OneToOneField(Ride, on_delete=models.CASCADE, related_name='review')
    user = models.ForeignKey('verify.Users', on_delete=models.CASCADE, related_name='reviews')
    driver = models.ForeignKey('verify.Drivers', on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField()  # 1-5
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reviews'
        indexes = [models.Index(fields=['driver']), models.Index(fields=['user'])]

def _hash_token(raw: str) -> str:
    """Return sha256 hex digest of raw token."""
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class DriverAPIKey(models.Model):
    driver = models.OneToOneField('verify.Drivers', on_delete=models.CASCADE, related_name='api_key')
    key_hash = models.CharField(max_length=64, unique=True, db_index=True,
                                help_text="sha256 hash of the token (raw token not stored).")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(blank=True, null=True, db_index=True)
    revoked = models.BooleanField(default=False)
    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'driver_api_key'
        indexes = [
            models.Index(fields=['driver']),
            models.Index(fields=['-last_used']),
        ]

    def __str__(self):
        return f"API Key for driver {self.driver_id} (revoked={self.revoked})"

    @classmethod
    def generate_raw_token(cls, nbytes: int = 32) -> str:
        """Generate a cryptographically secure URL-safe token (raw)."""
        return secrets.token_urlsafe(nbytes)

    @classmethod
    def create_for_driver(cls, driver, lifetime_days: int = None) -> str:
        """
        Create (or replace) an API key for the driver.
        Returns the raw token (show this to the caller only once).
        """
        raw = cls.generate_raw_token()
        key_hash = _hash_token(raw)

        # If there's already a key, replace it (or you could keep multiple)
        obj, created = cls.objects.update_or_create(
            driver=driver,
            defaults={
                'key_hash': key_hash,
                'revoked': False,
                'last_used': None,
                'expires_at': (timezone.now() + timedelta(days=lifetime_days)) if lifetime_days else None,
            }
        )
        return raw

    @classmethod
    def verify_token(cls, raw_token: str):
        """
        Return DriverAPIKey instance if token valid and not revoked/expired, else None.
        Also updates last_used timestamp.
        """
        if not raw_token:
            return None
        key_hash = _hash_token(raw_token)
        try:
            obj = cls.objects.get(key_hash=key_hash, revoked=False)
        except cls.DoesNotExist:
            return None
        if obj.expires_at and obj.expires_at < timezone.now():
            return None
        # Update last_used
        obj.last_used = timezone.now()
        obj.save(update_fields=['last_used'])
        return obj

    def revoke(self):
        self.revoked = True
        self.save(update_fields=['revoked'])