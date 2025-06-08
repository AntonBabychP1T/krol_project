# promapp/management/commands/runapscheduler.py
from django.core.management.base import BaseCommand
from django_apscheduler.jobstores import DjangoJobStore
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from promapp.tasks import daily_import_orders   # ← top-level import

class Command(BaseCommand):
    help = "Запускає APScheduler і планує імпорт замовлень щодня о 02:00"

    def handle(self, *args, **options):
        scheduler = BlockingScheduler()
        scheduler.add_jobstore(DjangoJobStore(), "default")

        # Тепер ми даємо APScheduler зрозумілий, імпортований callable:
        scheduler.add_job(
            daily_import_orders,
            trigger=CronTrigger(hour=2, minute=0),
            id="daily_import_orders",
            replace_existing=True,
            max_instances=1,
        )

        self.stdout.write(">>> APScheduler started: daily import scheduled at 02:00")
        try:
            scheduler.start()
        except KeyboardInterrupt:
            self.stdout.write(">>> APScheduler stopped")
