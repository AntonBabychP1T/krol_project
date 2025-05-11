from django import forms
from .models import Store


class OrderImportForm(forms.Form):
    PERIOD_CHOICES = [
        ("1_day", "Останній день"),
        ("7_days", "Останній тиждень"),
        ("30_days", "Останній місяць"),
        ("all", "Усі замовлення"),
        ("test", "Тестовий імпорт (10 останніх)"),
    ]
    period = forms.ChoiceField(
        choices=PERIOD_CHOICES, label="Виберіть період для імпорту"
    )

class OrderFilterForm(forms.Form):
    order_id = forms.IntegerField(required=False, label="ID замовлення")
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Дата створення (від)",
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Дата створення (до)",
    )
    client_first_name = forms.CharField(required=False, label="Ім'я клієнта")
    client_last_name = forms.CharField(required=False, label="Прізвище клієнта")
    phone = forms.CharField(required=False, label="Телефон")
    email = forms.CharField(required=False, label="Email")
    status_name = forms.CharField(required=False, label="Статус")
    source = forms.CharField(required=False, label="Джерело")

    stores = forms.ModelMultipleChoiceField(
        queryset=Store.objects.none(),
        required=False,
        label="Магазини",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields["stores"].queryset = user.stores.all()


class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ["store_name", "api_key"]
        labels = {
            "store_name": "Назва магазину",
            "api_key": "API ключ",
        }


class CommissionAnalyticsForm(forms.Form):
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), label="Дата початку"
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), label="Дата завершення"
    )
    exclude_cancelled = forms.BooleanField(
        required=False,
        label="Приховати відмінені замовлення"
    )

    # ---------- форма вибору періоду ----------
class InsightForm(forms.Form):
    PERIODS = [
        ("30", "Останні 30 днів"),
        ("90", "Останні 90 днів (квартал)"),
        ("custom", "Вказати свої дати"),
    ]
    period = forms.ChoiceField(choices=PERIODS, label="Період")
    start = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Початок"
    )
    end = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Кінець"
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("period") == "custom":
            if not cleaned.get("start") or not cleaned.get("end"):
                raise forms.ValidationError("Вкажіть обидві дати.")
            if cleaned["start"] > cleaned["end"]:
                raise forms.ValidationError("Початок має бути не пізніше кінця.")
        return cleaned
