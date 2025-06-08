from django.test import TestCase
from promapp.forms import InsightForm

class InsightFormTest(TestCase):
    def test_default_period(self):
        form = InsightForm(data={"period": "7", "start": "", "end": ""})
        self.assertTrue(form.is_valid())

    def test_custom_requires_dates(self):
        form = InsightForm(data={"period": "custom"})
        self.assertFalse(form.is_valid())
        self.assertIn("start", form.errors)
        self.assertIn("end", form.errors)
