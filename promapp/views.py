import json
from datetime import timedelta
from statistics import median

from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.db.models import Count
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
import requests
from datetime import datetime
import os

from .forms import (
    OrderImportForm, OrderFullImportForm, OrderFilterForm, 
    StoreForm, CommissionAnalyticsForm
)
from .models import Order, Product, Store

def index(request):
    # Головна сторінка – доступна всім
    return render(request, 'index.html')

@login_required
def orders_list(request):
    filter_form = OrderFilterForm(request.GET or None, user=request.user)
    user_stores = request.user.stores.all()
    orders = Order.objects.filter(store__in=user_stores).order_by('-date_created')
    
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
        if filter_form.cleaned_data.get('stores'):
            orders = orders.filter(store__in=filter_form.cleaned_data['stores'])
    
    paginator = Paginator(orders, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'orders_list.html', {'page_obj': page_obj, 'filter_form': filter_form})

@login_required
def analytics(request):
    """
    Об’єднана аналітика:
      1. Розподіл замовлень за статусами для магазинів поточного користувача.
      2. Графік комісії: для заданого періоду (введеного через форму) 
         – для кожного дня обчислюється медіанна комісія,
         – також обчислюється загальна середня комісія за весь період.
    """
    # Аналітика за статусами
    user_stores = request.user.stores.all()
    orders = Order.objects.filter(store__in=user_stores)
    status_data = orders.values('status_name').annotate(count=Count('id'))
    total_orders = orders.count()
    status_labels = []
    status_counts = []
    status_percentages = []
    for entry in status_data:
        status_labels.append(entry['status_name'])
        status_counts.append(entry['count'])
        percent = (entry['count'] / total_orders * 100) if total_orders > 0 else 0
        status_percentages.append(round(percent, 2))
    status_chart_data = {
        'labels': status_labels,
        'counts': status_counts,
        'percentages': status_percentages,
    }

    # Аналітика комісії
    form = CommissionAnalyticsForm(request.GET or None)
    daily_labels = []
    daily_medians = []
    overall_avg = None

    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date']
        orders_period = orders.filter(
            date_created__date__gte=start_date,
            date_created__date__lte=end_date
        ).order_by('date_created')
        all_commissions = []
        for order in orders_period:
            commission_data = order.cpa_commission
            if commission_data and commission_data.get("amount"):
                try:
                    all_commissions.append(float(commission_data.get("amount")))
                except (ValueError, TypeError):
                    continue
        overall_avg = round(sum(all_commissions) / len(all_commissions), 2) if all_commissions else 0

        current_date = start_date
        while current_date <= end_date:
            daily_orders = orders_period.filter(date_created__date=current_date)
            daily_commissions = []
            for order in daily_orders:
                commission_data = order.cpa_commission
                if commission_data and commission_data.get("amount"):
                    try:
                        daily_commissions.append(float(commission_data.get("amount")))
                    except (ValueError, TypeError):
                        continue
            daily_median = round(median(daily_commissions), 2) if daily_commissions else 0
            daily_labels.append(current_date.strftime("%Y-%m-%d"))
            daily_medians.append(daily_median)
            current_date += timedelta(days=1)
    commission_chart_data = {
        'labels': daily_labels,
        'daily_medians': daily_medians,
        'overall_avg': overall_avg,
    }

    context = {
        'status_chart_data': json.dumps(status_chart_data),
        'commission_chart_data': json.dumps(commission_chart_data),
        'commission_form': form,
    }
    return render(request, 'analytics.html', context)

@login_required
def import_orders_view(request):
    message = ""
    user_stores = request.user.stores.all()
    if request.method == "POST":
        store_id = request.POST.get('store')
        if not store_id:
            message = "Виберіть магазин!"
        else:
            try:
                store = user_stores.get(id=store_id)
                message = import_orders_for_store(store, period='test')
            except Store.DoesNotExist:
                message = "Магазин не знайдено!"
    return render(request, 'import_orders.html', {'message': message, 'stores': user_stores})

@login_required
def import_full_orders_view(request):
    message = ""
    user_stores = request.user.stores.all()
    if request.method == "POST":
        form = OrderFullImportForm(request.POST)
        store_id = request.POST.get('store')
        if form.is_valid() and store_id:
            try:
                store = user_stores.get(id=store_id)
                start_date = form.cleaned_data['start_date']
                end_date = form.cleaned_data['end_date']
                date_from = start_date.strftime("%Y-%m-%dT00:00:00")
                date_to = end_date.strftime("%Y-%m-%dT23:59:59")
                message = import_orders_full(date_from, date_to, store)
            except Store.DoesNotExist:
                message = "Магазин не знайдено!"
    else:
        form = OrderFullImportForm()
    return render(request, 'full_import_orders.html', {'form': form, 'message': message, 'stores': user_stores})

def import_orders_for_store(store, period='all'):
    url = "https://my.prom.ua/api/v1/orders/list"
    API_TOKEN = store.api_key
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
                    "store": store,
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
                ext_id = product_data.get("external_id")
                if not ext_id:
                    ext_id = str(product_data.get("id"))
                Product.objects.update_or_create(
                    order=order,
                    external_id=ext_id,
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

@login_required
def user_profile(request):
    if not request.user.is_authenticated:
        return redirect('login')
    user_stores = request.user.stores.all()
    if request.method == "POST":
        form = StoreForm(request.POST)
        if form.is_valid():
            store = form.save(commit=False)
            store.user = request.user
            store.save()
            return redirect('user_profile')
    else:
        form = StoreForm()
    return render(request, 'user_profile.html', {'stores': user_stores, 'form': form})

# Реєстрація, вхід, вихід
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout

def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('index')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

def user_login(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('index')
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})

def user_logout(request):
    logout(request)
    return redirect('index')
