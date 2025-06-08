from django.test import TestCase
from django.utils.dateparse import parse_datetime
from promapp.models import Store, Order, Product
from promapp.views import import_orders_for_store
from datetime import datetime, timedelta

class ImportOrdersTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            user_id=1,
            store_name="Тестовий",
            api_key="fake-token",
        )
        # замокаємо requests.get
        import requests
        self._real_get = requests.get
        def fake_get(url, headers, params, timeout):
            class R:
                status_code = 200
                def json(self):
                    return {
                        "orders": [
                            {
                                "id": 123,
                                "date_created": "2025-01-01T12:00:00",
                                "client_first_name": "Іван",
                                "client_second_name": "",
                                "client_last_name": "Петренко",
                                "client_id": 999,
                                "client_notes": "",
                                "phone": "380001112233",
                                "email": "a@example.com",
                                "price": "100.00",
                                "full_price": "110.00",
                                "delivery_address": "Kyiv",
                                "delivery_cost": 10,
                                "status": "new",
                                "status_name": "Новий",
                                "source": "portal",
                                "has_order_promo_free_delivery": False,
                                "dont_call_customer_back": False,
                                "delivery_option": {},
                                "delivery_provider_data": {},
                                "payment_option": {},
                                "payment_data": {},
                                "utm": {},
                                "cpa_commission": {"amount": "5.00"},
                                "ps_promotion": {},
                                "cancellation": {},
                                "products": [
                                    {
                                        "id": 1,
                                        "external_id": "SKU1",
                                        "image": "http://img.url/1.jpg",
                                        "quantity": 2,
                                        "price": "50.00",
                                        "url": "http://prod/1",
                                        "name": "Товар-1",
                                        "name_multilang": {"uk":"Товар-1"},
                                        "total_price": "100.00",
                                        "measure_unit": "шт.",
                                        "sku": "SKU1",
                                        "cpa_commission": {"amount": "2.50"},
                                    }
                                ]
                            }
                        ]
                    }
            return R()
        requests.get = fake_get

    def tearDown(self):
        import requests
        requests.get = self._real_get

    def test_import_creates_order_and_product(self):
        msg = import_orders_for_store(self.store, period="test")
        self.assertIn("Імпортовано 1", msg)
        order = Order.objects.get(pk=123)
        self.assertEqual(order.client_first_name, "Іван")
        prod = order.products.get(external_id="SKU1")
        self.assertEqual(prod.name, "Товар-1")
