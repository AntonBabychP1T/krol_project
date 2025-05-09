from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('orders/', views.orders_list, name='orders_list'),
    path('orders/import/', views.import_orders_view, name='import_orders_view'),
    path('analytics/', views.analytics, name='analytics'),
    path('profile/', views.user_profile, name='user_profile'),
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
]
