import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Count
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import requests
from datetime import datetime
from collections import defaultdict

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
    user_stores = request.user.stores.all()
    base_qs = Order.objects.filter(store__in=user_stores)

    # 1) Статуси
    status_agg = base_qs.values("status_name").annotate(count=Count("id"))
    total = base_qs.count()
    status_chart_data = {
        "labels": [e["status_name"] for e in status_agg],
        "counts": [e["count"] for e in status_agg],
        "percentages": [
            round(e["count"] * 100 / total, 2) if total else 0
            for e in status_agg
        ],
    }

    # 2) Дані для комісій + кількості
    form = CommissionAnalyticsForm(request.GET or None)
    daily_labels = []
    daily_sums = []
    daily_counts = []

    if form.is_valid():
        start = form.cleaned_data["start_date"]
        end   = form.cleaned_data["end_date"]
        exclude = form.cleaned_data["exclude_cancelled"]

        # базовий queryset за датами
        period_qs = base_qs.filter(
            date_created__date__range=(start, end)
        )
        if exclude:
            # прибираємо статус "Отменен"
            period_qs = period_qs.exclude(status_name__iexact="Отменен")

        # витягуємо лише дату та комісію
        raw = period_qs.values("date_created", "cpa_commission")

        by_date = defaultdict(list)
        for rec in raw:
            day = rec["date_created"].date()
            com = rec["cpa_commission"] or {}
            amt = com.get("amount")
            try:
                if amt is not None:
                    by_date[day].append(float(amt))
            except (ValueError, TypeError):
                continue

        days = (end - start).days + 1
        for i in range(days):
            day = start + timedelta(days=i)
            daily_labels.append(day.strftime("%Y-%m-%d"))

            # к-сть замовлень у цей день
            cnt = period_qs.filter(date_created__date=day).count()
            daily_counts.append(cnt)

            # сума комісій
            s = round(sum(by_date.get(day, [])), 2)
            daily_sums.append(s)

    commission_chart_data = {
        "labels":       daily_labels,
        "daily_sums":   daily_sums,
        "daily_counts": daily_counts,
    }

    return render(request, "analytics.html", {
        "status_chart_data":     json.dumps(status_chart_data),
        "commission_chart_data": json.dumps(commission_chart_data),
        "commission_form":       form,
    })


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
