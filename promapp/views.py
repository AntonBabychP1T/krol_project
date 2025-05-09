import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from statistics import median

from django.db.models import Count, Sum
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import requests
from datetime import datetime
import os

from .forms import (
    OrderImportForm, OrderFilterForm, 
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
    """
    Сторінка імпорту: вибір магазину + періоду, повідомлення про результат.
    """
    user_stores = request.user.stores.all()
    form = OrderImportForm(request.POST or None)
    message = ""

    if request.method == "POST" and form.is_valid():
        store_id = request.POST.get("store")
        period = form.cleaned_data["period"]

        if not store_id:
            message = "Виберіть магазин!"
        else:
            try:
                store = user_stores.get(id=store_id)
                message = import_orders_for_store(store, period=period)
            except Store.DoesNotExist:
                message = "Магазин не знайдено!"

    context = {
        "stores": user_stores,
        "form": form,
        "message": message,
    }
    return render(request, "import_orders.html", context)



def _to_decimal(val):
    """Безпечний Decimal → використовується лише для DecimalField."""
    if val in (None, "", "null"):
        return Decimal("0")
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))
    if isinstance(val, str):
        val = val.replace(",", ".").strip()
    try:
        return Decimal(val)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def import_orders_for_store(store, period="all"):
    base_url = getattr(store, "base_domain", "https://my.prom.ua")
    url = f"{base_url}/api/v1/orders/list"
    headers = {
        "Authorization": f"Bearer {store.api_key}",
        "Content-Type": "application/json",
    }

    now = datetime.utcnow()
    fltr = {}
    if period == "1_day":
        fltr["date_from"] = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    elif period == "7_days":
        fltr["date_from"] = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    elif period == "30_days":
        fltr["date_from"] = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")

    limit = 10 if period == "test" else 100
    offset = 0
    fetched = new_orders = updated_orders = 0

    while True:
        params = {**fltr, "limit": limit, "offset": offset}

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as exc:
            return f"Помилка запиту до API: {exc}"

        if resp.status_code != 200:
            return f"Помилка при імпорті даних: {resp.status_code} – {resp.text}"

        orders_chunk = resp.json().get("orders", [])
        if not orders_chunk:
            break

        for data in orders_chunk:
            order, created = Order.objects.update_or_create(
                pk=data["id"],
                defaults={
                    "store": store,
                    "date_created": parse_datetime(data.get("date_created")) or timezone.now(),
                    "client_first_name": data.get("client_first_name"),
                    "client_second_name": data.get("client_second_name"),
                    "client_last_name": data.get("client_last_name"),
                    "client_id": data.get("client_id"),
                    "client_notes": data.get("client_notes"),
                    "phone": data.get("phone"),
                    "email": data.get("email"),
                    "price": _to_decimal(data.get("price")),
                    "full_price": _to_decimal(data.get("full_price")),
                    "delivery_address": data.get("delivery_address"),
                    "delivery_cost": _to_decimal(data.get("delivery_cost")),
                    "status": data.get("status"),
                    "status_name": data.get("status_name"),
                    "source": data.get("source"),
                    "has_order_promo_free_delivery": data.get("has_order_promo_free_delivery"),
                    "dont_call_customer_back": data.get("dont_call_customer_back"),
                    "delivery_option": data.get("delivery_option"),
                    "delivery_provider_data": data.get("delivery_provider_data"),
                    "payment_option": data.get("payment_option"),
                    "payment_data": data.get("payment_data"),
                    "utm": data.get("utm"),
                    # JSONField — зберігаємо цілий об’єкт як прийшов
                    "cpa_commission": data.get("cpa_commission"),
                    "ps_promotion": data.get("ps_promotion"),
                    "cancellation": data.get("cancellation"),
                },
            )
            if created:
                new_orders += 1
            else:
                updated_orders += 1

            for prod in data.get("products", []):
                ext_id = prod.get("external_id") or str(prod.get("id"))
                Product.objects.update_or_create(
                    order=order,
                    external_id=ext_id,
                    defaults={
                        "image": prod.get("image"),
                        "quantity": prod.get("quantity"),
                        "price": _to_decimal(prod.get("price")),
                        "url": prod.get("url"),
                        "name": prod.get("name"),
                        "name_multilang": prod.get("name_multilang"),
                        "total_price": _to_decimal(prod.get("total_price")),
                        "measure_unit": prod.get("measure_unit"),
                        "sku": prod.get("sku"),
                        # теж JSONField
                        "cpa_commission": prod.get("cpa_commission"),
                    },
                )

        fetched += len(orders_chunk)
        if len(orders_chunk) < limit or period in {"1_day", "7_days", "30_days", "test"}:
            break
        offset += limit

    return f"Імпортовано {fetched} замовлень: {new_orders} нових, {updated_orders} оновлено."

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
