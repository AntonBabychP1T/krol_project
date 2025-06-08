from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class OrdersListViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        u = User.objects.create_user("test", "t@e.com", "pass")
        self.client.login(username="test", password="pass")

    def test_orders_page_status(self):
        resp = self.client.get(reverse("orders_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Замовлення")
