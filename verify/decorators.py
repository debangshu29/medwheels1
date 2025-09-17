# verify/decorators.py
from django.shortcuts import redirect
from functools import wraps
from .models import Employees, Roles, EmployeeRoles, Users

def ceo_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('ceo_login')   # or wherever you want to redirect
        try:
            user = Users.objects.get(pk=user_id)
            employee = Employees.objects.filter(user=user).first()
            if not employee:
                return redirect('ceo_login')
            ceo_role = Roles.objects.filter(name__iexact="CEO").first()
            if not ceo_role:
                return redirect('ceo_login')
            if not EmployeeRoles.objects.filter(employee=employee, role=ceo_role).exists():
                return redirect('ceo_login')
            # allowed
            return view_func(request, *args, **kwargs)
        except Users.DoesNotExist:
            return redirect('ceo_login')
    return _wrapped
