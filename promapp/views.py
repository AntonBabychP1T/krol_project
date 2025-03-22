from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.db.models import Count
from .forms import OrderImportForm, OrderFullImportForm, OrderFilterForm
from .models import Order, Product
import os
import requests
from datetime import datetime, timedelta
import json

def index(request):
    return render(request, 'index.html')

def orders_list(request):
    filter_form = OrderFilterForm(request.GET or None)
    orders = Order.objects.all().order_by('-date_created')
    
    if filter_form.is_valid():
        if filter_form.cleaned_data.get('order_id'):
            orders = orders.filter(id=filter_form.cleaned_data['order_id'])
        if filter_form.cleaned_data.get('start_date'):
            orders = orders.filter(date_created__gte=filter_form.cleaned_data['start_date'])
        if filter_form.cleaned_data.get('end_date'):
            orders = orders.filter(date_created__lte=filter_form.cleaned_data['end_date'])
        if filter_form.cleaned_data.get('client_first_name'):
            orders = orders.filter(client_first_name__icontains=filter_form.cleaned_data['client_first_name'])
        if filter_form.cleaned_data.get('client_last_name'):
            orders = orders.filter(client_last_name__icontains=filter_form.cleaned_data['client_last_name'])
        if filter_form.cleaned_data.get('phone'):
            orders = orders.filter(phone__icontains=filter_form.cleaned_data['phone'])
        if filter_form.cleaned_data.get('email'):
            orders = orders.filter(email__icontains=filter_form.cleaned_data['email'])
        if filter_form.cleaned_data.get('status_name'):
            orders = orders.filter(status_name__icontains=filter_form.cleaned_data['status_name'])
        if filter_form.cleaned_data.get('source'):
            orders = orders.filter(source__icontains=filter_form.cleaned_data['source'])
    
    paginator = Paginator(orders, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'orders_list.html', {'page_obj': page_obj, 'filter_form': filter_form})

def import_orders(period='all'):
    """
    Функція імпорту замовлень із API за заданий період.
    Якщо period=='test' – імпортується 10 останніх замовлень.
    """
    url = "https://my.prom.ua/api/v1/orders/list"
    API_TOKEN = os.environ.get("API_TOKEN")
    if not API_TOKEN:
        return "API_TOKEN не задано!"
    
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }
    
    params = {}
    if period == '1_day':
        params['date_from'] = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    elif period == '7_days':
        params['date_from'] = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    elif period == '30_days':
        params['date_from'] = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    elif period == 'test':
        params['limit'] = 10
    else:
        params['limit'] = 100
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        return f"Помилка запиту до API: {e}"
    
    if response.status_code == 200:
        orders_data = response.json().get('orders', [])
        new_orders = 0
        updated_orders = 0
        for order_data in orders_data:
            order, created = Order.objects.update_or_create(
                id=order_data["id"],
                defaults={
                    "date_created": order_data.get("date_created"),
                    "client_first_name": order_data.get("client_first_name"),
                    "client_second_name": order_data.get("client_second_name"),
                    "client_last_name": order_data.get("client_last_name"),
                    "client_id": order_data.get("client_id"),
                    "client_notes": order_data.get("client_notes"),
                    "phone": order_data.get("phone"),
                    "email": order_data.get("email"),
                    "price": order_data.get("price"),
                    "full_price": order_data.get("full_price"),
                    "delivery_address": order_data.get("delivery_address"),
                    "delivery_cost": order_data.get("delivery_cost"),
                    "status": order_data.get("status"),
                    "status_name": order_data.get("status_name"),
                    "source": order_data.get("source"),
                    "has_order_promo_free_delivery": order_data.get("has_order_promo_free_delivery"),
                    "dont_call_customer_back": order_data.get("dont_call_customer_back"),
                    "delivery_option": order_data.get("delivery_option"),
                    "delivery_provider_data": order_data.get("delivery_provider_data"),
                    "payment_option": order_data.get("payment_option"),
                    "payment_data": order_data.get("payment_data"),
                    "utm": order_data.get("utm"),
                    "cpa_commission": order_data.get("cpa_commission"),
                    "ps_promotion": order_data.get("ps_promotion"),
                    "cancellation": order_data.get("cancellation"),
                }
            )
            if created:
                new_orders += 1
            else:
                updated_orders += 1
            
            for product_data in order_data.get("products", []):
                Product.objects.update_or_create(
                    order=order,
                    external_id=product_data.get("external_id"),
                    defaults={
                        "image": product_data.get("image"),
                        "quantity": product_data.get("quantity"),
                        "price": product_data.get("price"),
                        "url": product_data.get("url"),
                        "name": product_data.get("name"),
                        "name_multilang": product_data.get("name_multilang"),
                        "total_price": product_data.get("total_price"),
                        "measure_unit": product_data.get("measure_unit"),
                        "sku": product_data.get("sku"),
                        "cpa_commission": product_data.get("cpa_commission"),
                    }
                )
        return f"Імпортовано {len(orders_data)} замовлень: {new_orders} нових, {updated_orders} оновлено."
    else:
        return f"Помилка при імпорті даних: {response.status_code}"

def import_orders_view(request):
    """
    Сторінка для тестового імпорту (10 останніх замовлень).
    """
    message = ""
    if request.method == "POST":
        message = import_orders(period='test')
    return render(request, 'import_orders.html', {'message': message})

def import_full_orders_view(request):
    """
    Сторінка для повного імпорту за заданий період.
    Користувач задає дату початку та завершення, і система імпортує замовлення, яких ще немає в базі.
    """
    message = ""
    if request.method == "POST":
        form = OrderFullImportForm(request.POST)
        if form.is_valid():
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
            date_from = start_date.strftime("%Y-%m-%dT00:00:00")
            date_to = end_date.strftime("%Y-%m-%dT23:59:59")
            message = import_orders_full(date_from, date_to)
    else:
        form = OrderFullImportForm()
    return render(request, 'full_import_orders.html', {'form': form, 'message': message})

def import_orders_full(date_from, date_to):
    """
    Функція для імпорту замовлень за заданий період.
    """
    url = "https://my.prom.ua/api/v1/orders/list"
    API_TOKEN = os.environ.get("API_TOKEN")
    if not API_TOKEN:
        return "API_TOKEN не задано!"
    
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }
    
    params = {
        'date_from': date_from,
        'date_to': date_to,
        'limit': 1000
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
    except requests.exceptions.RequestException as e:
        return f"Помилка запиту до API: {e}"
    
    if response.status_code == 200:
        orders_data = response.json().get('orders', [])
        new_orders = 0
        updated_orders = 0
        for order_data in orders_data:
            order, created = Order.objects.update_or_create(
                id=order_data["id"],
                defaults={
                    "date_created": order_data.get("date_created"),
                    "client_first_name": order_data.get("client_first_name"),
                    "client_second_name": order_data.get("client_second_name"),
                    "client_last_name": order_data.get("client_last_name"),
                    "client_id": order_data.get("client_id"),
                    "client_notes": order_data.get("client_notes"),
                    "phone": order_data.get("phone"),
                    "email": order_data.get("email"),
                    "price": order_data.get("price"),
                    "full_price": order_data.get("full_price"),
                    "delivery_address": order_data.get("delivery_address"),
                    "delivery_cost": order_data.get("delivery_cost"),
                    "status": order_data.get("status"),
                    "status_name": order_data.get("status_name"),
                    "source": order_data.get("source"),
                    "has_order_promo_free_delivery": order_data.get("has_order_promo_free_delivery"),
                    "dont_call_customer_back": order_data.get("dont_call_customer_back"),
                    "delivery_option": order_data.get("delivery_option"),
                    "delivery_provider_data": order_data.get("delivery_provider_data"),
                    "payment_option": order_data.get("payment_option"),
                    "payment_data": order_data.get("payment_data"),
                    "utm": order_data.get("utm"),
                    "cpa_commission": order_data.get("cpa_commission"),
                    "ps_promotion": order_data.get("ps_promotion"),
                    "cancellation": order_data.get("cancellation"),
                }
            )
            if created:
                new_orders += 1
            else:
                updated_orders += 1
            
            for product_data in order_data.get("products", []):
                Product.objects.update_or_create(
                    order=order,
                    external_id=product_data.get("external_id"),
                    defaults={
                        "image": product_data.get("image"),
                        "quantity": product_data.get("quantity"),
                        "price": product_data.get("price"),
                        "url": product_data.get("url"),
                        "name": product_data.get("name"),
                        "name_multilang": product_data.get("name_multilang"),
                        "total_price": product_data.get("total_price"),
                        "measure_unit": product_data.get("measure_unit"),
                        "sku": product_data.get("sku"),
                        "cpa_commission": product_data.get("cpa_commission"),
                    }
                )
        return f"Імпортовано {len(orders_data)} замовлень: {new_orders} нових, {updated_orders} оновлено."
    else:
        return f"Помилка при імпорті даних: {response.status_code}"

def analytics(request):
    # Групування замовлень за статусом та обчислення кількості для кожного статусу
    status_data = Order.objects.values('status_name').annotate(count=Count('id'))
    total = Order.objects.count()

    labels = []
    percentages = []
    counts = []
    for entry in status_data:
        labels.append(entry['status_name'])
        counts.append(entry['count'])
        percent = (entry['count'] / total * 100) if total > 0 else 0
        percentages.append(round(percent, 2))
    
    chart_data = {
        'labels': labels,
        'percentages': percentages,
        'counts': counts,
    }
    
    # Передаємо дані як JSON рядок у шаблон
    return render(request, 'analytics.html', {'chart_data': json.dumps(chart_data)})
