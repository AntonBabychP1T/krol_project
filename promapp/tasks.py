# promapp/tasks.py
from datetime import date, timedelta
from promapp.views import import_orders_for_store
from promapp.models import Store

def daily_import_orders():
    """
    Імпортує всі замовлення за вчорашній день для кожного магазину.
    """
    yesterday = date.today() - timedelta(days=1)
    for store in Store.objects.all():
        import_orders_for_store(
            store,
            period="custom",
            start_date=yesterday,
            end_date=yesterday
        )
