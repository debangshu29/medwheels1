
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from allauth.account.signals import user_signed_up
from allauth.socialaccount.models import SocialAccount
from django.db import transaction

User = get_user_model()

def _get_social_account(auth_user, provider_name='google'):
    try:
        return SocialAccount.objects.filter(user=auth_user, provider=provider_name).first()
    except Exception:
        return None

def sync_auth_user_to_custom(auth_user, request=None):
    """
    Safely sync a django auth user to your custom Users table.
    - Only set auth_provider='google' when a Google SocialAccount exists.
    - If creating custom user and no social account, default to 'local'.
    - Do not overwrite an existing auth_provider to 'google' unless the SocialAccount exists.
    """
    from .models import Users  # local import to avoid circulars

    email = (auth_user.email or "").lower()
    name = (auth_user.get_full_name() or auth_user.username or "").strip()

    # Check if a google social account exists for this auth user
    sa_google = _get_social_account(auth_user, provider_name='google')
    profile_picture = ""
    if sa_google:
        extra = sa_google.extra_data or {}
        profile_picture = extra.get('picture') or extra.get('picture_url') or ""
        # prefer social 'name' if present
        if extra.get('name'):
            name = extra.get('name')

    # Find existing custom user by email
    custom_user = Users.objects.filter(email__iexact=email).first()

    if not custom_user:
        # create with provider = 'google' if social account exists else 'local'
        provider = 'google' if sa_google else 'local'
        custom_user = Users.objects.create(
            name=name or email.split('@')[0],
            email=email,
            phone_number="",
            password=None,
            auth_provider=provider,
            profile_picture=profile_picture or "",
            user_type='customer',
        )
    else:
        # Update only when we have social data OR fields are missing.
        updated = False

        if profile_picture and (not getattr(custom_user, 'profile_picture', None)):
            custom_user.profile_picture = profile_picture
            updated = True

        if name and (not getattr(custom_user, 'name', None) or custom_user.name.strip() == ""):
            custom_user.name = name
            updated = True

        # Only set auth_provider to 'google' if a google SocialAccount exists.
        if sa_google and custom_user.auth_provider != 'google':
            custom_user.auth_provider = 'google'
            updated = True

        # Do NOT set auth_provider to 'google' when sa_google is None.
        # (We don't overwrite local -> google accidentally)

        if updated:
            custom_user.save()

    # set session keys so your existing views continue to work
    if request is not None:
        request.session['user_id'] = custom_user.id
        request.session['user_name'] = custom_user.name

    return custom_user


@receiver(user_signed_up)
def allauth_user_signed_up(request, user, **kwargs):
    # Called when a new user signs up via allauth (social or local).
    with transaction.atomic():
        sync_auth_user_to_custom(user, request=request)


@receiver(user_logged_in)
def auth_user_logged_in(sender, request, user, **kwargs):
    # Called when any user logs in (including social logins).
    with transaction.atomic():
        sync_auth_user_to_custom(user, request=request)
