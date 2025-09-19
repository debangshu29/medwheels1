from django.urls import path
from . import views

urlpatterns = [
    path('accounts/', views.signup_login_page, name='signup_login'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
    path('', views.home, name='home'),
    path('logout/', views.logout_view, name='logout'),
    path('admin_login/', views.ceo_login, name='ceo_login'),
    path('ceo/', views.ceo_dashboard, name='ceo_dashboard'),
    path("driver/driver_apply/", views.driver_application, name="driver_application"),
    path('driver/set-password/<uidb64>/<token>/', views.driver_set_password, name='driver_set_password'),
    path('driver/driver_login/', views.driver_login, name='driver_login'),
    path('driver/', views.driver_page, name='driver_page'),
    path('driver/logout/', verify_views.driver_logout, name='driver_logout'),

]
