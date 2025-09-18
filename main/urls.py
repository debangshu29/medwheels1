from django.contrib import admin
from django.urls import path, include
from . import views
urlpatterns = [
    path('service/', views.service_view, name='service'),
    path('service/api/nearby/', views.api_nearby_ambulances, name='service_nearby'),
    path('service/see_price/', views.api_see_price, name='service_see_price'),
    path('service/estimate/', views.service_estimate, name='service_estimate'),
    path('driver/dashboard/', views.driver_dashboard, name='driver_dashboard'),
    path('api/driver/live/', views.api_driver_live_update, name='api_driver_live_update'),
    path('api/estimate/', views.api_estimate, name='api_estimate'),
    path('api/book_ride/', views.api_book_ride, name='api_book_ride'),
    path('api/nearby/', views.api_nearby_ambulances, name='api_nearby_ambulances'),
    path('api/request_ambulance_type/', views.api_request_ambulance_type, name='api_request_ambulance_type'),
    path('find_driver/<int:ride_id>/', views.find_driver_view, name='find_driver'),
    path('api/driver/respond/', views.api_driver_respond, name='api_driver_respond'),
    path('api_cancel_ride/<int:ride_id>/', views.api_cancel_ride, name='api_cancel_ride'),
    path('debug/channel_layer/', views.debug_channel_layer, name='debug_channel_layer'),

]
