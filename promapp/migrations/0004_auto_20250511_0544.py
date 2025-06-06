# Generated by Django 3.2.25 on 2025-05-11 05:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('promapp', '0003_auto_20250323_1007'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='delivery_status',
            field=models.CharField(blank=True, help_text="Статус доставки: наприклад, 'delivered', 'refused', 'pending'", max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='tracking_number',
            field=models.CharField(blank=True, help_text='Номер ТТН або інший ідентифікатор відправлення', max_length=100, null=True),
        ),
    ]
