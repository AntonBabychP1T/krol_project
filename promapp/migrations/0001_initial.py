# Generated by Django 3.2.25 on 2025-03-20 08:34

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigIntegerField(primary_key=True, serialize=False)),
                ('date_created', models.DateTimeField()),
                ('client_first_name', models.CharField(max_length=255)),
                ('client_second_name', models.CharField(blank=True, max_length=255, null=True)),
                ('client_last_name', models.CharField(max_length=255)),
                ('client_id', models.BigIntegerField()),
                ('client_notes', models.TextField(blank=True, null=True)),
                ('phone', models.CharField(max_length=50)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('price', models.CharField(max_length=50)),
                ('full_price', models.CharField(max_length=50)),
                ('delivery_address', models.CharField(max_length=500)),
                ('delivery_cost', models.IntegerField()),
                ('status', models.CharField(max_length=50)),
                ('status_name', models.CharField(max_length=50)),
                ('source', models.CharField(max_length=50)),
                ('has_order_promo_free_delivery', models.BooleanField(default=False)),
                ('dont_call_customer_back', models.BooleanField(default=False)),
                ('delivery_option', models.JSONField()),
                ('delivery_provider_data', models.JSONField()),
                ('payment_option', models.JSONField()),
                ('payment_data', models.JSONField(blank=True, null=True)),
                ('utm', models.JSONField()),
                ('cpa_commission', models.JSONField()),
                ('ps_promotion', models.JSONField(blank=True, null=True)),
                ('cancellation', models.JSONField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Store',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('store_name', models.CharField(max_length=255)),
                ('api_key', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stores', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(max_length=255)),
                ('image', models.URLField()),
                ('quantity', models.FloatField()),
                ('price', models.CharField(max_length=50)),
                ('url', models.URLField()),
                ('name', models.CharField(max_length=255)),
                ('name_multilang', models.JSONField()),
                ('total_price', models.CharField(max_length=50)),
                ('measure_unit', models.CharField(max_length=50)),
                ('sku', models.CharField(blank=True, max_length=255, null=True)),
                ('cpa_commission', models.JSONField()),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='products', to='promapp.order')),
            ],
            options={
                'unique_together': {('order', 'external_id')},
            },
        ),
    ]
