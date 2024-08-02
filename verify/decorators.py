from django.shortcuts import redirect

def driver_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_driver:
            return redirect('driver_dashboard')  # Redirect to driver dashboard if not authenticated or not a driver
        return view_func(request, *args, **kwargs)
    return wrapper