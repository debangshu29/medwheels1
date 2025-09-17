
from django.contrib import admin
from django.urls import path, include
from verify import views as verify_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/api/drivers/pending/', verify_views.admin_pending_drivers, name='admin_pending_drivers'),
    path('admin/api/drivers/approve/', verify_views.admin_approve_driver, name='admin_approve_driver'),
    path('admin/api/drivers/reject/', verify_views.admin_reject_driver, name='admin_reject_driver'),
    path('admin/', admin.site.urls),
    path('', include('main.urls')),
    path('', include('verify.urls')),
    path('accounts/', include('allauth.urls')),  # allauth handles Google + signup
    path('logout/', verify_views.logout_view, name='logout'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

