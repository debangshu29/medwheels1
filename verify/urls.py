from django.contrib import admin
from django.urls import path, include
from verify import views

urlpatterns = [
    path('', views.main_view, name="main"),
    path('signup/', views.signup_view, name="signup"),
    path('login/', views.login_view, name="login"),
    path('logout/', views.logout_view, name="logout"),
    path('driver/dashboard/', views.driver_dashboard_view, name='dashboard'),

]