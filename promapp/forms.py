# promapp/forms.py

from django import forms
from .models import Order, Store

class OrderImportForm(forms.Form):
    PERIOD_CHOICES = [
        ("1_day", "Останній день"),
        ("7_days", "Останній тиждень"),
        ("30_days", "Останній місяць"),
        ("all", "Усі замовлення"),
        ("test", "Тестовий імпорт (10 останніх)"),
        ("custom", "Власний період"),
    ]
    period = forms.ChoiceField(
        choices=PERIOD_CHOICES,
        label="Період імпорту",
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Дата початку",
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Дата завершення",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("period") == "custom":
            sd = cleaned.get("start_date")
            ed = cleaned.get("end_date")
            if not sd or not ed:
                raise forms.ValidationError("Для власного періоду вкажіть обидві дати.")
            if sd > ed:
                raise forms.ValidationError("Початкова дата не може бути пізніше за кінцеву.")
        return cleaned


class OrderFilterForm(forms.Form):
    order_id = forms.IntegerField(label="ID замовлення", required=False)
    start_date = forms.DateField(
        label="Дата створення (від)", 
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"})
    )
    end_date = forms.DateField(
        label="Дата створення (до)", 
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"})
    )
    client_first_name = forms.CharField(label="Ім'я клієнта", required=False,
                                        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}))
    client_last_name  = forms.CharField(label="Прізвище клієнта", required=False,
                                        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}))
    phone = forms.CharField(label="Телефон", required=False,
                            widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}))
    email = forms.EmailField(label="Email", required=False,
                             widget=forms.EmailInput(attrs={"class": "form-control form-control-sm"}))

    # Збираємо усі унікальні статуси з бази
    STATUS_CHOICES = [("", "Всі статуси")] + [
        (s["status_name"], s["status_name"])
        for s in Order.objects.order_by().values("status_name").distinct()
    ]
    status_name = forms.ChoiceField(
        label="Статус",
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"})
    )

    # І всі унікальні джерела
    SOURCE_CHOICES = [("", "Всі джерела")] + [
        (s["source"], s["source"])
        for s in Order.objects.order_by().values("source").distinct()
    ]
    source = forms.ChoiceField(
        label="Джерело",
        choices=SOURCE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"})
    )

    # Магазини (як раніше)
    stores = forms.ModelMultipleChoiceField(
        label="Магазини",
        queryset=Store.objects.none(),  # заповнимо у вію
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select form-select-sm"})
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["stores"].queryset = user.stores.all()


class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ["store_name", "api_key"]
        widgets = {
            "store_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Назва вашого магазину"
            }),
            "api_key": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "API-ключ із Prom"
            }),
        }
        labels = {
            "store_name": "Назва магазину",
            "api_key":    "API-ключ"
        }

class CommissionAnalyticsForm(forms.Form):
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Дата початку"
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Дата завершення"
    )
    exclude_cancelled = forms.BooleanField(
        required=False,
        label="Виключити скасовані замовлення"
    )


class InsightForm(forms.Form):
    PERIODS = [
        ("30", "Останні 30 днів"),
        ("90", "Останні 90 днів (квартал)"),
        ("custom", "Власний період"),
    ]
    period = forms.ChoiceField(choices=PERIODS, label="Період для AI-аналізу")
    start = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Початок"
    )
    end = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Кінець"
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned["period"] == "custom":
            if not cleaned.get("start") or not cleaned.get("end"):
                raise forms.ValidationError("Вкажіть обидві дати для власного періоду.")
            if cleaned["start"] > cleaned["end"]:
                raise forms.ValidationError("Початок має бути <= кінця.")
        return cleaned
