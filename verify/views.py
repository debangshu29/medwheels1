# views.py
from django.shortcuts import render, redirect
from django.contrib.auth.hashers import make_password, check_password
from django.urls import reverse
from django.contrib.auth import get_user_model, authenticate, login as auth_login
from django.db import transaction

from django.utils import timezone
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_GET, require_POST
from .models import Users, Employees, Roles, EmployeeRoles, Drivers, DriverDocuments
import json
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.contrib.auth import get_user_model
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse
from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.conf import settings

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404
from .decorators import ceo_required
UserModel = get_user_model()


def driver_page(request):
    return render(request, "driver_page.html")
def _make_unique_username(base):
    base = (base or "user").strip()
    username = base
    suffix = 0
    while UserModel.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base}{suffix}"
    return username

def create_or_get_django_user_for_email(email, phone=None, password=None):
    email = (email or "").strip().lower()
    if not email:
        return None
    django_user = UserModel.objects.filter(email__iexact=email).first()
    if django_user:
        return django_user
    # build username (prefer phone if you want login by phone as username)
    username_base = phone if phone else email.split('@')[0]
    username = _make_unique_username(username_base)
    if password:
        u = UserModel.objects.create_user(username=username, email=email, password=password)
    else:
        # create and set unusable password — driver will set it later
        u = UserModel.objects.create_user(username=username, email=email)
        u.set_unusable_password()
        u.save()
    return u

def build_set_password_link(django_user):
    uid = urlsafe_base64_encode(force_bytes(django_user.pk))
    token = default_token_generator.make_token(django_user)
    path = reverse('driver_set_password', args=[uid, token])
    return settings.SITE_DOMAIN.rstrip('/') + path

def _is_ceo_or_staff(user):
    return user.is_authenticated and user.is_staff
def _get_employee_id_from_session(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return None
    try:
        user = Users.objects.get(pk=user_id)
        emp = Employees.objects.filter(user=user).first()
        return emp.id if emp else None
    except Users.DoesNotExist:
        return None

def signup_login_page(request):
    show = request.GET.get('show', '')
    signup_success = request.GET.get('signup', '')
    context = {
        'show': show,
        'signup_success': signup_success,
    }
    return render(request, "login.html", context)


def _make_unique_username(base):
    """
    Return a username that does not exist in the auth_user table.
    Uses base (usually before-@ of email) and appends numbers if needed.
    """
    base = (base or "user").strip()
    username = base
    suffix = 0
    while UserModel.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base}{suffix}"
    return username


def signup(request):
    if request.method != "POST":
        return redirect(reverse('signup_login'))

    name = (request.POST.get("name") or "").strip()
    email = (request.POST.get("email") or "").strip().lower()
    phone = (request.POST.get("mobile") or "").strip()
    password = request.POST.get("password") or ""
    user_type = request.POST.get("user_type", "customer")

    # basic validation
    if not (name and email and phone and password):
        return render(request, "login.html", {
            "error_signup": "Please fill all fields.",
            "show": "signup"
        })

    # sanitize and check duplicate
    if Users.objects.filter(email__iexact=email).exists():
        return render(request, "login.html", {
            "error_signup": "Email already exists.",
            "show": "signup"
        })
    if phone and Users.objects.filter(phone_number=phone).exists():
        return render(request, "login.html", {
            "error_signup": "Phone number already registered.",
            "show": "signup"
        })

    # create Django auth user (so django-allauth and social logins can link)
    with transaction.atomic():
        username_base = email.split('@')[0]
        username = _make_unique_username(username_base)

        if not UserModel.objects.filter(email__iexact=email).exists():
            django_user = UserModel.objects.create_user(username=username, email=email, password=password)
        else:
            django_user = UserModel.objects.filter(email__iexact=email).first()

        # create custom Users record
        hashed = make_password(password)
        custom_user, created = Users.objects.get_or_create(
            email=email,
            defaults={
                'name': name,
                'phone_number': phone,
                'password': hashed,
                'user_type': user_type,
                'auth_provider': 'local',
            }
        )
        if not created:
            # update fields if needed
            custom_user.name = name
            custom_user.phone_number = phone
            custom_user.password = hashed
            custom_user.save()

    # Redirect to the accounts login page (show login panel)
    return redirect(f"{reverse('signup_login')}?show=login&signup=1")


def login(request):
    if request.method != "POST":
        return redirect(f"{reverse('signup_login')}?show=login")

    phone = (request.POST.get("mobile") or "").strip()
    password = request.POST.get("password") or ""

    if not (phone and password):
        return render(request, "login.html", {
            "error_login": "Please enter phone and password.",
            "show": "login"
        })

    try:
        user = Users.objects.get(phone_number=phone)
    except Users.DoesNotExist:
        return render(request, "login.html", {
            "error_login": "User not found.",
            "show": "login"
        })
    if user.user_type != "customer":
        return render(request, "login.html", {
            "error_login": "Only customers can log in here. Please use the correct login portal.",
            "show": "login"
        })

    if check_password(password, user.password):
        # Try to find or create a matching Django auth user and log them in
        email = (user.email or "").strip().lower()
        try:
            django_user = UserModel.objects.filter(email__iexact=email).first()
        except Exception:
            django_user = None

        if not django_user:
            # create one so allauth/social paths can work consistently later
            username_base = email.split('@')[0] if email else f"user{user.id}"
            username = _make_unique_username(username_base)
            django_user = UserModel.objects.create_user(username=username, email=email, password=password)
        else:
            # ensure the password matches the auth user as well (optional)
            # We won't reset django_user password blindly here for security.
            pass

        # authenticate & login Django user so signals (user_logged_in) can run
        auth = authenticate(request, username=django_user.username, password=password)
        if auth:
            auth_login(request, auth)
            # the user_logged_in signal will sync and set request.session['user_id']
            # but as backup, ensure your session keys are set
        else:
            # fallback: if authenticate failed, still set your custom session
            request.session['user_id'] = user.id
            request.session['user_name'] = user.name

        return redirect(reverse('home'))

    return render(request, "login.html", {
        "error_login": "Invalid password.",
        "show": "login"
    })


def home(request):
    user = None
    first_name = None

    user_id = request.session.get('user_id')
    if user_id:
        try:
            user = Users.objects.get(pk=user_id)
            if user.name:
                first_name = user.name.strip().split()[0]
            else:
                if user.email:
                    first_name = user.email.split('@')[0]
                else:
                    first_name = user.phone_number or ''
        except Users.DoesNotExist:
            request.session.flush()
            user = None

    return render(request, "home.html", {"user": user, "first_name": first_name})


def logout_view(request):
    # flush both Django session and custom session data
    from django.contrib.auth import logout as auth_logout
    auth_logout(request)
    request.session.flush()
    return redirect(reverse('home'))


def ceo_login(request):
    """
    CEO login: authenticate using custom Users table (phone + password),
    then verify employee -> has CEO role in EmployeeRoles.
    """
    if request.method == "GET":
        return render(request, "admin_login.html")

    # POST
    phone = (request.POST.get("mobile") or "").strip()
    password = request.POST.get("password") or ""

    if not phone or not password:
        return render(request, "admin_login.html", {"error": "Please enter mobile and password."})

    try:
        custom_user = Users.objects.get(phone_number=phone)
    except Users.DoesNotExist:
        return render(request, "admin_login.html", {"error": "User not found."})

    # password stored hashed using Django make_password
    if not check_password(password, custom_user.password or ""):
        return render(request, "admin_login.html", {"error": "Invalid credentials."})

    # verify employee record exists and has CEO role
    try:
        employee = Employees.objects.get(user=custom_user)
    except Employees.DoesNotExist:
        return render(request, "admin_login.html", {"error": "No employee profile found for this user."})

    # find role 'CEO' (case-insensitive)
    ceo_role = Roles.objects.filter(name__iexact="CEO").first()
    if not ceo_role:
        return render(request, "admin_login.html", {"error": "CEO role not configured. Contact admin."})

    has_ceo = EmployeeRoles.objects.filter(employee=employee, role=ceo_role).exists()
    if not has_ceo:
        return render(request, "admin_login.html", {"error": "You are not authorized to access the admin panel."})

    # success: set session
    request.session['user_id'] = custom_user.id
    request.session['user_name'] = custom_user.name
    request.session['is_ceo'] = True

    # optionally set expiry for CEO session
    # request.session.set_expiry(24 * 3600)  # 1 day

    return redirect(reverse('ceo_dashboard'))

def ceo_dashboard(request):
    return render(request, "ceo_dashboard.html", {"ceo": request.session.get('user_name')})


def driver_application(request):
    if request.method == "POST":
        # 1. Create the User (driver applicant)
        user = Users.objects.create(
            name=request.POST['fullname'],
            email=request.POST['email'],
            phone_number=request.POST['phone'],
            auth_provider="local",
            user_type="driver",
            created_at=timezone.now(),
        )

        # 2. Create the Driver profile
        driver = Drivers.objects.create(
            user=user,
            full_name=request.POST['fullname'],
            gender=request.POST['gender'],
            dob=request.POST['dob'],
            address=request.POST['address'],
            experience=request.POST['experience'],
            emergency_contact=request.POST['emergency_contact'],
            status="pending",
            created_at=timezone.now(),
        )

        # 3. Create Driver Documents
        DriverDocuments.objects.create(
            driver=driver,
            photo=request.FILES['photo'],
            license_no=request.POST['license_no'],
            license_scan=request.FILES['license_scan'],
            issue_date=request.POST['issue_date'],
            expiry_date=request.POST['expiry_date'],
            vehicle=request.POST['vehicle'],
            gov_id_number=request.POST['id-card'],
            gov_id=request.FILES['gov_id'],
            uploaded_at=timezone.now(),
            status="pending",
        )

        return render(request, "driver_success.html", {"driver": driver})

    return render(request, "driver_application.html")


def _driver_to_dict(driver, request=None):
    # build a JSON-safe dict to send to front-end
    docs = list(driver.documents.all())  # related_name 'documents'
    doc = docs[0] if docs else None
    media = {}
    if doc:
        # if you serve media via MEDIA_URL, construct full url for frontend:
        base = request.build_absolute_uri('/')[:-1] if request else ''
        media = {
            'photo_url': request.build_absolute_uri(doc.photo.url) if doc.photo else '',
            'license_scan_url': request.build_absolute_uri(doc.license_scan.url) if doc.license_scan else '',
            'gov_id_url': request.build_absolute_uri(doc.gov_id.url) if doc.gov_id else '',
        }
    return {
        'id': driver.id,
        'user_id': driver.user_id,
        'full_name': driver.full_name,
        'phone': driver.user.phone_number,
        'email': driver.user.email,
        'status': driver.status,
        'created_at': driver.created_at.isoformat() if driver.created_at else '',
        'license_no': doc.license_no if doc else '',
        'vehicle': doc.vehicle if doc else '',
        'experience': driver.experience,
        'media': media,
    }

@require_GET
def admin_pending_drivers(request):
    if not request.session.get('is_ceo'):
        return HttpResponseForbidden(json.dumps({'ok': False, 'error': 'forbidden'}), content_type='application/json')
    qs = Drivers.objects.filter(status='pending').order_by('-created_at')
    out = []
    for d in qs:
        doc = DriverDocuments.objects.filter(driver=d).order_by('-uploaded_at').first()
        media = {}
        if doc:
            if getattr(doc, 'photo', None) and hasattr(doc.photo, 'url'):
                media['photo_url'] = request.build_absolute_uri(doc.photo.url)
            if getattr(doc, 'license_scan', None) and hasattr(doc.license_scan, 'url'):
                media['license_scan_url'] = request.build_absolute_uri(doc.license_scan.url)
            if getattr(doc, 'gov_id', None) and hasattr(doc.gov_id, 'url'):
                media['gov_id_url'] = request.build_absolute_uri(doc.gov_id.url)

        out.append({
            'id': d.id,
            'full_name': d.full_name,
            'phone': getattr(d.user, 'phone_number', '') if d.user_id else '',
            'email': getattr(d.user, 'email', '') if d.user_id else '',
            'experience': d.experience if d.experience is not None else 0,
            'gender': d.gender,
            'address': d.address,
            'license_no': getattr(doc, 'license_no', '') if doc else '',
            'vehicle': getattr(doc, 'vehicle', '') if doc else '',
            'status': d.status,
            'created_at': d.created_at.isoformat() if d.created_at else None,
            'media': media
        })
    return JsonResponse({'pending': out})


@require_POST
def admin_approve_driver(request):
    if not request.session.get('is_ceo'):
        return HttpResponseForbidden(json.dumps({'ok': False, 'error': 'forbidden'}), content_type='application/json')
    try:
        payload = json.loads(request.body.decode('utf-8'))
        driver_id = payload.get('driver_id')
    except Exception:
        return HttpResponseBadRequest(json.dumps({'ok': False, 'error': 'invalid json'}), content_type='application/json')

    if not driver_id:
        return JsonResponse({'ok': False, 'error': 'driver_id required'}, status=400)

    # restrict to CEO: here you should check session or Django auth permissions.
    # Example check (you should replace with your real check)
    if not request.session.get('user_id'):
        return HttpResponseForbidden(json.dumps({'ok': False, 'error': 'forbidden'}), content_type='application/json')

    with transaction.atomic():
        driver = get_object_or_404(Drivers, pk=driver_id)
        # set verified_by to current employee if available
        # you may map session user -> Employees row; here we leave null or try to find employee
        emp = None
        emp_user_id = request.session.get('user_id')
        if emp_user_id:
            # try to map to your Employees record (if exists)
            emp = Employees.objects.filter(user__id=emp_user_id).first()
        driver.status = 'approved'
        driver.verified_by = emp
        driver.save()

        # ensure there's a DriverDocuments record (if applicable)
        doc = DriverDocuments.objects.filter(driver=driver).order_by('-uploaded_at').first()
        if doc:
            doc.status = 'approved'
            doc.verified_by = emp
            # ensure uploaded_at exists (optional)
            if not doc.uploaded_at:
                doc.uploaded_at = timezone.now()
            doc.save()

        # Ensure a custom Users record exists for this driver user (they may be linked already)
        # The driver.user should exist (foreign key to Users). If not, create Users row.
        custom_user = None
        if driver.user_id:
            custom_user = driver.user
        else:
            # create a Users row with phone and email if provided in form (adjust accordingly)
            # You might not have email; require email in application form.
            custom_user = Users.objects.create(
                name=driver.full_name,
                email=getattr(driver, 'email', '') or '',
                phone_number=getattr(driver, 'phone', '') or '',
                user_type='driver',
                auth_provider='local'
            )
            driver.user = custom_user
            driver.save()

        # create Django auth user (so we can issue token link)
        django_user = create_or_get_django_user_for_email(custom_user.email, phone=custom_user.phone_number)

        # Build set-password link
        link = build_set_password_link(django_user)

        # Send email to driver
        subject = "MedWheels — Your driver application is approved"
        set_password_url = link
        message = f"""
Hi {driver.full_name},

Your driver application for MedWheels has been approved.

Login id (username): {custom_user.phone_number or django_user.username}
Please set your password using the link below (this link expires after a while for security):

{set_password_url}

If you did not apply, ignore this email.

Thanks,
MedWheels Team
"""
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [custom_user.email], fail_silently=False)

    return JsonResponse({'ok': True, 'message': 'Driver approved and email sent.'})


@require_POST
def admin_reject_driver(request):
    if not request.session.get('is_ceo'):
        return HttpResponseForbidden(json.dumps({'ok': False, 'error': 'forbidden'}), content_type='application/json')
    try:
        payload = json.loads(request.body.decode('utf-8'))
        driver_id = payload.get('driver_id')
        reason = payload.get('reason') or ''
    except Exception:
        return HttpResponseBadRequest(json.dumps({'ok': False, 'error': 'invalid json'}), content_type='application/json')

    if not driver_id:
        return JsonResponse({'ok': False, 'error': 'driver_id required'}, status=400)

    if not request.session.get('user_id'):
        return HttpResponseForbidden(json.dumps({'ok': False, 'error': 'forbidden'}), content_type='application/json')

    with transaction.atomic():
        driver = get_object_or_404(Drivers, pk=driver_id)
        emp = None
        emp_user_id = request.session.get('user_id')
        if emp_user_id:
            emp = Employees.objects.filter(user__id=emp_user_id).first()
        driver.status = 'rejected'
        # optionally save reason somewhere (add a field or related model)
        driver.verified_by = emp
        driver.save()

        doc = DriverDocuments.objects.filter(driver=driver).order_by('-uploaded_at').first()
        if doc:
            doc.status = 'rejected'
            doc.verified_by = emp
            if not doc.uploaded_at:
                doc.uploaded_at = timezone.now()
            doc.save()

        # notify driver
        # assume driver.user.email exists
        email = driver.user.email if driver.user_id and driver.user.email else None
        if email:
            subject = "MedWheels — Your driver application"
            message = f"Hi {driver.full_name},\n\nYour application has been rejected.\n\nReason: {reason}\n\nIf you think this is a mistake contact support.\n\nThanks,\nMedWheels"
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)

    return JsonResponse({'ok': True, 'message': 'Driver rejected and email sent (if email present).'})


def driver_set_password(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        django_user = UserModel.objects.get(pk=uid)
    except Exception:
        django_user = None

    if django_user is None or not default_token_generator.check_token(django_user, token):
        return render(request, 'driver_set_password_invalid.html', status=400)

    if request.method == 'POST':
        pwd1 = request.POST.get('password1')
        pwd2 = request.POST.get('password2')
        if not pwd1 or pwd1 != pwd2:
            return render(request, 'driver_set_password.html', {'error': 'Passwords must match.'})
        # set django password
        django_user.set_password(pwd1)
        django_user.save()

        # update custom Users model (if present)
        try:
            custom_user = Users.objects.filter(email__iexact=django_user.email).first()
            if custom_user:
                custom_user.password = make_password(pwd1)
                custom_user.auth_provider = 'local'
                custom_user.save()
        except Exception:
            pass

        # optionally auto-login user:
        # from django.contrib.auth import login as auth_login, authenticate
        # auth = authenticate(username=django_user.username, password=pwd1)
        # if auth: auth_login(request, auth)

        return render(request, 'driver_set_password_done.html')

    return render(request, 'driver_set_password.html', {})

# -------------------------
# decorator to protect driver pages
# -------------------------
def driver_required(view_func):
    """
    Decorator: allow access only if session user_id corresponds to an approved driver.
    Usage: @driver_required
    """
    def _wrapped(request, *args, **kwargs):
        user_id = request.session.get('user_id')
        if not user_id:
            # not logged in
            return redirect(reverse('driver_login') + '?next=' + request.path)
        try:
            custom_user = Users.objects.get(pk=user_id)
        except Users.DoesNotExist:
            request.session.flush()
            return redirect(reverse('driver_login'))
        # must be a driver type
        if (getattr(custom_user, 'user_type', None) or '').lower() != 'driver':
            return HttpResponseForbidden("Only drivers allowed.")
        # check Drivers row exists & is approved
        if not Drivers.objects.filter(user=custom_user, status='approved').exists():
            return HttpResponseForbidden("Driver profile not approved or missing.")
        return view_func(request, *args, **kwargs)
    _wrapped.__name__ = getattr(view_func, '__name__', 'wrapped')
    return _wrapped

# -------------------------
# POST login view for drivers
# -------------------------
@require_http_methods(["GET", "POST"])
def driver_login(request):
    """
    Login endpoint for drivers only.
    - Accepts POST: mobile + password
    - Ensures Users.user_type == 'driver' and Drivers exists and status == 'approved'
    - Sets session keys: user_id, user_name and redirects to driver dashboard
    """
    if request.method == 'GET':
        return render(request, 'driver_login.html', {})

    # POST
    mobile = (request.POST.get('mobile') or '').strip()
    password = request.POST.get('password') or ''

    if not mobile or not password:
        return render(request, 'driver_login.html', {'error': 'Enter mobile and password.'})

    try:
        custom_user = Users.objects.get(phone_number=mobile)
    except Users.DoesNotExist:
        return render(request, 'driver_login.html', {'error': 'User not found.'})

    # must be driver type
    if (getattr(custom_user, 'user_type', '') or '').lower() != 'driver':
        return render(request, 'driver_login.html', {'error': 'This login is for drivers only.'})

    # driver profile must exist
    driver_profile = Drivers.objects.filter(user=custom_user).first()
    if not driver_profile:
        return render(request, 'driver_login.html', {'error': 'Driver profile not found. Contact support.'})

    # driver must be approved
    if driver_profile.status != 'approved':
        return render(request, 'driver_login.html',
                      {'error': f'Your application is not approved (status: {driver_profile.status}).'})

    # password stored in custom Users.password (hashed with make_password). It could be NULL if driver hasn't set password yet
    stored_hash = custom_user.password or ''
    if not stored_hash:
        # user has no password set: ask them to set password (you already send set-password link on approve)
        return render(request, 'driver_login.html', {
            'error': 'No password set. Check your email for the set-password link or request password reset.'
        })

    if not check_password(password, stored_hash):
        return render(request, 'driver_login.html', {'error': 'Invalid credentials.'})

    # login success: set session and optionally ensure a Django auth user exists and is logged in
    request.session['user_id'] = custom_user.id
    request.session['user_name'] = custom_user.name or custom_user.phone_number
    request.session['is_driver'] = True

    # Also create/ensure corresponding Django auth user so standard auth-based decorators work (optional):
    # create a UserModel if not exists (we prefer not to reset password here)
    try:
        django_user = UserModel.objects.filter(email__iexact=(custom_user.email or '')).first()
    except Exception:
        django_user = None

    if not django_user:
        # create an auth user with unusable password so signals/allauth still work later
        username_base = custom_user.phone_number or (custom_user.email or 'driver').split('@')[0]
        username = username_base
        suffix = 0
        while UserModel.objects.filter(username=username).exists():
            suffix += 1
            username = f"{username_base}{suffix}"
        django_user = UserModel.objects.create_user(username=username, email=custom_user.email or '')
        django_user.set_unusable_password()
        django_user.save()

    # Do Django login if you want (optional) - requires authenticate if password set in auth_user
    # auth = authenticate(request, username=django_user.username, password=password)
    # if auth:
    #     django_login(request, auth)

    # redirect to driver dashboard (change name to your url name)
    next_url = request.GET.get('next') or reverse('driver_dashboard')
    return redirect(next_url)




