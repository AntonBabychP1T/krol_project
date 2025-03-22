import os
import json
import requests
from django.core.management.base import BaseCommand
from promapp.models import Order, Product
from datetime import datetime

class Command(BaseCommand):
    help = "Fetch orders from PROM API and update or create them in the database"

    def handle(self, *args, **options):
        API_TOKEN = os.environ.get("API_TOKEN")
        if not API_TOKEN:
            raise Exception("API_TOKEN не задано!")

        # Оновлений URL для отримання замовлень
        API_URL = "https://my.prom.ua/api/v1/orders"
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
        }

        # Визначаємо дату для запиту (якщо є параметри для фільтрації)
        date_from = '2024-04-28T12:50:34'  # Задаємо дату з якої потрібно отримувати замовлення
        date_to = '2024-04-30T12:50:34'    # Задаємо дату до якої потрібно отримувати замовлення

        params = {
            'limit': 10
        }

        # Виконуємо запит до API
        response = requests.get(API_URL, headers=headers, params=params)
        if response.status_code != 200:
            self.stderr.write(f"Error fetching orders: {response.status_code}")
            return

        data = response.json()
        orders_data = data.get("orders", [])
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
            # Обробка товарів у замовленні
            for product_data in order_data.get("products", []):
                # Використовуємо комбінацію order і external_id для уникнення дублікатів.
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
            if created:
                self.stdout.write(f"Created order {order.id}")
            else:
                self.stdout.write(f"Updated order {order.id}")
