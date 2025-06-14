import os
import json
from datetime import date, timedelta, datetime as dt
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from django.contrib import messages
import re

import requests
import logging
import threading

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
from django.db.models import (
    Count, Sum, Avg, DecimalField, Q      # ← Avg та Q
)
from django.contrib.postgres.fields.jsonb import KeyTextTransform  # ← для доступу до JSON‑поля
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
AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")
TOKEN_LIMIT = os.getenv("OPENAI_TOKEN_LIMIT", 2000)

def index(request):
    return render(request, "index.html")

from decimal import Decimal, InvalidOperation

def _to_float(val):
    """Надійно перетворює JSON‑рядок на float або 0.0"""
    try:
        if val in (None, "", "none"):
            return 0.0
        return float(re.sub(r"[^\d.\-]", "", str(val)))
    except (ValueError, InvalidOperation):
        return 0.0

def build_payload(user, start, end):
    qs = Order.objects.filter(
        store__in=user.stores.all(),
        date_created__date__range=(start, end)
    )

    delivered = qs.filter(delivery_status="delivered")
    refused   = qs.filter(delivery_status="refused")
    cancelled = qs.filter(status_name__iexact="Отменен")

    # —— комісія та ціна для всіх замовлень (у Python, аби уникнути помилок CAST) ——
    comm_values = [
        _to_float((c or {}).get("amount"))
        for c in qs.values_list("cpa_commission", flat=True)
    ]
    price_values = [
        _to_float(p) for p in qs.values_list("price", flat=True)
    ]

    commission_total = round(sum(comm_values), 2)
    commission_avg   = round(commission_total / len([v for v in comm_values if v]), 2) if comm_values else 0
    revenue_gross    = round(sum(price_values), 2)

    # —— топ‑товари без «проблемних» CAST ——
    top_raw = (
        Product.objects
        .filter(order__in=qs)
        .values("name")
        .annotate(
            sold_qty      = Sum("quantity"),
            delivered_qty = Sum("quantity", filter=Q(order__delivery_status="delivered")),
            refused_qty   = Sum("quantity", filter=Q(order__delivery_status="refused")),
        )
        .order_by("-sold_qty")[:15]
    )

    # обчислюємо середню комісію/ціну для кожного товару вже в Python
    top_items = []
    for t in top_raw:
        prod_qs = Product.objects.filter(order__in=qs, name=t["name"])
        p_comm  = [_to_float(p.cpa_commission.get("amount")) for p in prod_qs if p.cpa_commission]
        p_price = [_to_float(p.price) for p in prod_qs]

        top_items.append({
            "name":          t["name"][:60],
            "sold":          int(t["sold_qty"] or 0),
            "delivered":     int(t["delivered_qty"] or 0),
            "refused":       int(t["refused_qty"] or 0),
            "avg_commission": round(sum(p_comm)  / len(p_comm), 2) if p_comm else 0,
            "avg_price":      round(sum(p_price) / len(p_price), 2) if p_price else 0,
        })

    return {
        "period": f"{start} → {end}",
        "orders_total":       qs.count(),
        "orders_delivered":   delivered.count(),
        "orders_refused":     refused.count(),
        "orders_cancelled":   cancelled.count(),
        "revenue_gross":      revenue_gross,
        "commission_total":   commission_total,
        "commission_avg":     commission_avg,
        "delivery_status_distribution": {
            s: qs.filter(delivery_status=s).count()
            for s in ("delivered", "in_warehouse", "refused", "no_tracking")
        },
        "top_items": top_items,
    }


@login_required
def ai_insights(request):
    form = InsightForm(request.GET or None, initial={"period": "30"})
    insights = None
    payload_json = None
    truncated = False
    

    if form.is_valid():
        # Визначення дат
        today = dt.today()
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
        {
            "role": "system",
            "content": (
            "You are an e‑commerce financial analyst. "
            "The shop uses a **dropshipping** model (goods stored at suppliers’ warehouses). "
            "Gross revenue ≠ net profit. Prom commission is a proxy of margin: "
            "• High commission → healthy margin  • Commission < 30 UAH → risky (may be <1 USD profit). "
            "Delivery statuses:\n"
            " • delivered – money received\n"
            " • in_warehouse – parcel waiting at Nova Poshta; >5 days = high risk of refusal\n"
            " • refused – direct loss\n"
            " • no_tracking – parcel not sent or tracking lost\n"
            "Cancellation (status_name = 'Отменен') also means loss."
            """ Respond in **valid HTML** only (no Markdown). 
            Use:
            – `<h3>` for section titles,
            – `<ul><li>` for bullet lists,
            – `<table>` for the top-items table.
            Wrap the whole answer in a single `<div>`. """
            "Give the answer in Ukrainian"
            )
        },
        {
            "role": "user",
            "content": (
            "Here is 90‑day shop summary as JSON ↓. "
            "Please return output in **three blocks**:\n"
            "### 1. KPI\n"
            "• Orders total / delivered / refused / cancelled  \n"
            "• Gross revenue  \n"
            "• Prom commission total & avg per order  \n"
            "• Avg delivery lead‑time (use in_warehouse count if possible)\n"
            "### 2. Problems (max 5 bullets)\n"
            "### 3. Action plan (max 5 bullets) – concrete, measurable, adapted to DROPSHIPPING reality.\n"
            "Also include a small Markdown table (≤ 10 rows) of top items with columns: "
            "`Name | Sold | Delivered | Refused | Avg Price | Avg Commission` and highlight rows "
            "where Avg Commission < 30 UAH or Refused / Sold > 20 %.\n\n"
            f"```json\n{payload_json}\n```"
            )
        }
        ]
        try:
            resp = openai_client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                temperature=0.5,
                max_tokens=3000,     # збільшили ліміт
            )
            choice = resp.choices[0]
            insights = choice.message.content.strip()
            # якщо модель обрізала текст, finish_reason == 'length'
            if choice.finish_reason == 'length':
                if resp and resp.choices and resp.choices[0].finish_reason == "length":
                    truncated = True
                logger.warning("AI response was truncated due to max_tokens")
        except Exception as e:
            logger.error("AI request failed: %s", e, exc_info=True)
            insights = f"Не вдалося звернутися до AI: {e}"

    return render(request, "ai_insights.html", {
    "form": form,
    "insights": insights,
    "payload_json": payload_json,
    "truncated": truncated,
    })

@login_required
def orders_list(request):
    # 1️⃣ Форма фільтрів
    filter_form = OrderFilterForm(request.GET or None, user=request.user)

    # 2️⃣ Базовий QS: тільки по магазинах користувача + prefetch products
    qs = (
        Order.objects
        .filter(store__in=request.user.stores.all())
        .order_by('-date_created')
        .prefetch_related('products')    # <-- тільки ця, бо related_name='products'
    )

    # 3️⃣ Накладемо фільтри
    if filter_form.is_valid():
        cd = filter_form.cleaned_data
        if cd.get('order_id'):
            qs = qs.filter(id=cd['order_id'])
        if cd.get('start_date'):
            qs = qs.filter(date_created__date__gte=cd['start_date'])
        if cd.get('end_date'):
            qs = qs.filter(date_created__date__lte=cd['end_date'])
        if cd.get('status_name'):
            qs = qs.filter(status_name=cd['status_name'])
        if cd.get('source'):
            qs = qs.filter(source=cd['source'])
        # ми приберемо фільтр за stores, бо виводу магазину більше нема

    # 4️⃣ Пагінація
    paginator   = Paginator(qs, 10)
    page_number = request.GET.get('page')
    page_obj    = paginator.get_page(page_number)

    # 5️⃣ Залишаємо всі GET-параметри без 'page' для пагінації
    params = request.GET.copy()
    params.pop('page', None)
    params = params.urlencode()

    return render(request, 'orders_list.html', {
        'filter_form': filter_form,
        'page_obj':    page_obj,
        'params':      params,
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
    form = OrderImportForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        store_id = request.POST.get("store")
        period   = form.cleaned_data["period"]
        start_dt = form.cleaned_data.get("start_date")
        end_dt   = form.cleaned_data.get("end_date")

        if not store_id:
            messages.error(request, "⚠️ Виберіть магазин.")
            return redirect("import_orders_view")

        try:
            store = user_stores.get(id=store_id)
        except Store.DoesNotExist:
            messages.error(request, "Магазин не знайдено.")
            return redirect("import_orders_view")

        # --- запуск у фоновому daemon‑потоці -----------------
        def _run_import():
            try:
                if period == "custom":
                    import_orders_for_store(store, period, start_dt, end_dt)
                else:
                    import_orders_for_store(store, period)
                logger.info("Імпорт %s завершено", store.store_name)
            except Exception as exc:          # логуємо — не ламаємо весь Django
                logger.exception("Помилка імпорту: %s", exc)

        threading.Thread(target=_run_import, daemon=True).start()
        messages.info(
            request,
            "✅ Імпорт запущено у фоні. Дані оновляться незабаром."
        )
        return redirect("import_orders_view")

    return render(request, "import_orders.html", {
        "stores": user_stores,
        "form":   form,
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
