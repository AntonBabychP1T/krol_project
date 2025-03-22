from django.db import models
from django.contrib.auth.models import User

class Order(models.Model):
    id = models.BigIntegerField(primary_key=True)  # ID замовлення
    date_created = models.DateTimeField()
    client_first_name = models.CharField(max_length=255)
    client_second_name = models.CharField(max_length=255, blank=True, null=True)
    client_last_name = models.CharField(max_length=255)
    client_id = models.BigIntegerField()
    client_notes = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=50)
    email = models.EmailField(blank=True, null=True)
    price = models.CharField(max_length=50)
    full_price = models.CharField(max_length=50)
    delivery_address = models.CharField(max_length=500)
    delivery_cost = models.IntegerField()
    status = models.CharField(max_length=50)
    status_name = models.CharField(max_length=50)
    source = models.CharField(max_length=50)
    has_order_promo_free_delivery = models.BooleanField(default=False)
    dont_call_customer_back = models.BooleanField(default=False)
    
    # Збереження вкладених структур як JSONField (Django 3.1+)
    delivery_option = models.JSONField()
    delivery_provider_data = models.JSONField()
    payment_option = models.JSONField()
    payment_data = models.JSONField(blank=True, null=True)
    utm = models.JSONField(blank=True, null=True)
    cpa_commission = models.JSONField()
    ps_promotion = models.JSONField(blank=True, null=True)
    cancellation = models.JSONField(blank=True, null=True)
    
    def __str__(self):
        return f"Order #{self.id} ({self.status_name})"


class Product(models.Model):
    order = models.ForeignKey(Order, related_name='products', on_delete=models.CASCADE)
    external_id = models.CharField(max_length=255)
    image = models.URLField()
    quantity = models.FloatField()
    price = models.CharField(max_length=50)
    url = models.URLField()
    name = models.CharField(max_length=255)
    name_multilang = models.JSONField()
    total_price = models.CharField(max_length=50)
    measure_unit = models.CharField(max_length=50)
    sku = models.CharField(max_length=255, blank=True, null=True)
    cpa_commission = models.JSONField()
    
    class Meta:
        unique_together = (("order", "external_id"),)

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.measure_unit})"

class Store(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stores')
    store_name = models.CharField(max_length=255)
    api_key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.store_name