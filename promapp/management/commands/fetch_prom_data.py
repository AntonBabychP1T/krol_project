from django.core.management.base import BaseCommand
from promapp.models import Store, PromData
import requests

class Command(BaseCommand):
    help = 'Fetch data from PROM API for all stores'

    def handle(self, *args, **options):
        stores = Store.objects.all()
        for store in stores:
            api_key = store.api_key
            # Побудуйте URL згідно з документацією PROM API
            url = f'https://api.prom.ua/some_endpoint?api_key={api_key}'
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                # Збереження даних. Налаштуйте обробку даних згідно зі структурою відповіді API.
                PromData.objects.create(store=store, data=data)
                self.stdout.write(self.style.SUCCESS(f"Data fetched for {store.store_name}"))
            else:
                self.stdout.write(self.style.ERROR(f"Failed to fetch data for {store.store_name}"))
