import os
import json
from datetime import timedelta, datetime as dt
from decimal import Decimal, InvalidOperation
from collections import defaultdict
import re

import requests
import logging
import threading

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
from django.db.models import Count, Sum, DecimalField
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from openai import OpenAI

from .forms import (
    OrderImportForm,
    OrderFilterForm,
    StoreForm,
    CommissionAnalyticsForm,
    InsightForm,
)
from .models import Order, Product, Store

# Ініціалізуємо логгер та OpenAI-клієнта
logger = logging.getLogger(__name__)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def index(request):
    return render(request, "index.html")


def build_payload(user, start, end):
    stores = user.stores.all()
    orders = Order.objects.filter(
        store__in=stores,
        date_created__date__range=(start, end)
    )

    # ————— Python-рівнева обробка full_price —————
    revenues = []
    for order_id, raw_price in orders.values_list('id', 'full_price'):
        if raw_price:
            # видаляємо все, крім цифр, крапок і ком
            cleaned = re.sub(r'[^\d\.,]', '', raw_price).replace(',', '.')
            try:
                revenues.append(Decimal(cleaned))
            except InvalidOperation:
                logger.error("Невірний full_price для заказу %s: %r", order_id, raw_price)
    total_revenue = sum(revenues) if revenues else Decimal('0')

    cancels = orders.filter(status_name__iexact="Отменен").count()
    comm_total = sum(
        float((c or {}).get("amount", 0))
        for c in orders.values_list("cpa_commission", flat=True)
    )

    top_items = (
        Product.objects.filter(order__in=orders)
        .values("name")
        .annotate(qty=Sum("quantity"))
        .order_by("-qty")[:10]
    )

    return {
        "period": f"{start}→{end}",
        "orders": orders.count(),
        "revenue": float(total_revenue),
        "avg_order": float(total_revenue) / orders.count() if orders.count() else 0,
        "cancel_pct": round(cancels * 100 / orders.count(), 2) if orders.count() else 0,
        "commission_total": round(comm_total, 2),
        "top_items": [{"name": t["name"][:60], "qty": int(t["qty"])} for t in top_items],
    }



@login_required
def ai_insights(request):
    form = InsightForm(request.GET or None, initial={"period": "30"})
    insights = None
    payload_json = None

    if form.is_valid():
        # Визначення дат
        today = date.today()
        if form.cleaned_data["period"] == "30":
            start, end = today - timedelta(days=29), today
        elif form.cleaned_data["period"] == "90":
            start, end = today - timedelta(days=89), today
        else:
            start, end = form.cleaned_data["start"], form.cleaned_data["end"]

        # Підготовка payload
        payload = build_payload(request.user, start, end)
        payload_json = json.dumps(payload, ensure_ascii=False)

        # Логування payload для аналізу
        logger.debug("AI payload for user %s: %s", request.user.username, payload_json)

        messages = [
            {"role": "system",
             "content": "Ви досвідчений e-commerce аналітик. Дайте короткий аналіз і 5 конкретних порад."},
            {"role": "user",
             "content": f"Статистика магазину:\n```json\n{payload_json}\n```"},
        ]

        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4.1-nano",
                messages=messages,
                temperature=0.5,
                max_tokens=500,
            )
            insights = resp.choices[0].message.content.strip()
            logger.debug("AI response: %s", insights)
        except Exception as e:
            logger.error("AI request failed: %s", e, exc_info=True)
            insights = f"Не вдалося звернутися до AI: {e}"

    return render(request, "ai_insights.html", {
        "form": form,
        "insights": insights,
        "payload_json": payload_json,
    })

@login_required
def orders_list(request):
    filter_form = OrderFilterForm(request.GET or None, user=request.user)
    user_stores = request.user.stores.all()
    orders = Order.objects.filter(store__in=user_stores).order_by("-date_created")

    if filter_form.is_valid():
        cd = filter_form.cleaned_data
        if cd.get("order_id"):
            orders = orders.filter(id=cd["order_id"])
        if cd.get("start_date"):
            orders = orders.filter(date_created__gte=cd["start_date"])
        if cd.get("end_date"):
            orders = orders.filter(date_created__lte=cd["end_date"])
        if cd.get("client_first_name"):
            orders = orders.filter(client_first_name__icontains=cd["client_first_name"])
        if cd.get("client_last_name"):
            orders = orders.filter(client_last_name__icontains=cd["client_last_name"])
        if cd.get("phone"):
            orders = orders.filter(phone__icontains=cd["phone"])
        if cd.get("email"):
            orders = orders.filter(email__icontains=cd["email"])
        if cd.get("status_name"):
            orders = orders.filter(status_name__icontains=cd["status_name"])
        if cd.get("source"):
            orders = orders.filter(source__icontains=cd["source"])
        if cd.get("stores"):
            orders = orders.filter(store__in=cd["stores"])

    paginator = Paginator(orders, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "orders_list.html", {
        "page_obj": page_obj,
        "filter_form": filter_form,
    })


@login_required
def analytics(request):
    user_stores = request.user.stores.all()
    base_qs = Order.objects.filter(store__in=user_stores)

    # 1) Розподіл за статусами
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

    # 2) Комісії та кількість замовлень
    form = CommissionAnalyticsForm(request.GET or None)
    daily_labels, daily_sums, daily_counts = [], [], []

    if form.is_valid():
        start, end = form.cleaned_data["start_date"], form.cleaned_data["end_date"]
        qs = base_qs.filter(date_created__date__range=(start, end))
        if form.cleaned_data.get("exclude_cancelled"):
            qs = qs.exclude(status_name__iexact="Отменен")

        raw = qs.values("date_created", "cpa_commission")
        by_date = defaultdict(list)
        for r in raw:
            d = r["date_created"].date()
            amt = (r["cpa_commission"] or {}).get("amount")
            try:
                if amt is not None:
                    by_date[d].append(float(amt))
            except (ValueError, TypeError):
                continue

        days = (end - start).days + 1
        for i in range(days):
            day = start + timedelta(days=i)
            daily_labels.append(day.strftime("%Y-%m-%d"))
            daily_sums.append(round(sum(by_date.get(day, [])), 2))
            daily_counts.append(qs.filter(date_created__date=day).count())

        # 3) Топ-товари з пагінацією
        top_qs = (
            Product.objects.filter(order__in=qs)
            .values("name")
            .annotate(total_qty=Sum("quantity"))
            .order_by("-total_qty")
        )
        prod_paginator = Paginator(top_qs, 5)
        products_page = prod_paginator.get_page(request.GET.get("product_page", 1))
    else:
        products_page = None

    return render(request, "analytics.html", {
        "status_chart_data": json.dumps(status_chart_data),
        "commission_chart_data": json.dumps({
            "labels": daily_labels,
            "daily_sums": daily_sums,
            "daily_counts": daily_counts,
        }),
        "commission_form": form,
        "products_page": products_page,
    })


def _to_decimal(val):
    """
    Видаляємо з рядка все, крім цифр, крапок/ком, приводимо до Decimal.
    """
    if val in (None, "", "null"):
        return Decimal("0")
    raw = str(val)
    # лишаємо цифри, крапку, кому і мінус
    cleaned = re.sub(r"[^\d\.,-]", "", raw)
    # замінюємо кому на крапку
    cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def import_orders_for_store(store, period="all", start_date=None, end_date=None):

    """
    Функція залишається без змін, тільки додаємо обробку custom-періоду
    і на вході приймаємо date_from, date_to як ISO-рядки.
    """
    base_url = getattr(store, "base_domain", "https://my.prom.ua")
    url = f"{base_url}/api/v1/orders/list"
    headers = {
        "Authorization": f"Bearer {store.api_key}",
        "Content-Type": "application/json",
    }

    now = dt.utcnow()
    fltr = {}
    if period == "1_day":
        fltr["date_from"] = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    elif period == "7_days":
        fltr["date_from"] = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    elif period == "30_days":
        fltr["date_from"] = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    elif period == "custom" and start_date and end_date:
        fltr["date_from"] = start_date.strftime("%Y-%m-%dT00:00:00")
        fltr["date_to"]   = end_date.strftime("%Y-%m-%dT23:59:59")

    limit = 10 if period == "test" else 100
    offset = 0

    while True:
        params = {**fltr, "limit": limit, "offset": offset}
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            # тут можна логувати помилку
            return

        chunk = resp.json().get("orders", [])
        if not chunk:
            break

        for data in chunk:
            dpd = data.get("delivery_provider_data") or {}
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
                    "cpa_commission": data.get("cpa_commission"),
                    "ps_promotion": data.get("ps_promotion"),
                    "cancellation": data.get("cancellation"),
                    "delivery_status":    dpd.get("unified_status"),
                    "tracking_number":    dpd.get("declaration_number"),
                },
            )
            if order.status_name == "Виконано" and not order.tracking_number:
                order.delivery_status = "no_tracking"
                order.save(update_fields=["delivery_status"])

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
                        "cpa_commission": prod.get("cpa_commission"),
                    },
                )

        offset += limit
        if len(chunk) < limit:
            break


@login_required
def import_orders_view(request):
    user_stores = request.user.stores.all()
    # Більше не передаємо user=request.user
    form = OrderImportForm(request.POST or None)
    message = ""

    if request.method == "POST" and form.is_valid():
        store_id = request.POST.get("store")
        period = form.cleaned_data["period"]
        start = form.cleaned_data.get("start_date")
        end   = form.cleaned_data.get("end_date")

        if not store_id:
            message = "Виберіть магазин!"
        else:
            try:
                store = user_stores.get(id=store_id)
                # Якщо обрано власний період - передаємо start/end, інакше period
                if period == "custom":
                    message = import_orders_for_store(store, period, start, end)
                else:
                    message = import_orders_for_store(store, period)
            except Store.DoesNotExist:
                message = "Магазин не знайдено!"

    return render(request, "import_orders.html", {
        "stores":  user_stores,
        "form":    form,
        "message": message,
    })


@login_required
def user_profile(request):
    user_stores = request.user.stores.all()
    if request.method == "POST":
        form = StoreForm(request.POST)
        if form.is_valid():
            store = form.save(commit=False)
            store.user = request.user
            store.save()
            return redirect("user_profile")
    else:
        form = StoreForm()
    return render(request, "user_profile.html", {
        "stores": user_stores,
        "form": form,
    })


def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("index")
    else:
        form = UserCreationForm()
    return render(request, "registration/register.html", {"form": form})


def user_login(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("index")
    else:
        form = AuthenticationForm()
    return render(request, "registration/login.html", {"form": form})


def user_logout(request):
    logout(request)
    return redirect("index")
