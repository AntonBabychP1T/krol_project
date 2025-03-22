from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('orders/', views.orders_list, name='orders_list'),
    path('orders/import/', views.import_orders_view, name='import_orders_view'),
    path('orders/full-import/', views.import_full_orders_view, name='import_full_orders_view'),
    path('analytics/', views.analytics, name='analytics'),
]
