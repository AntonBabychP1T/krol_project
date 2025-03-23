from django import forms
from .models import Store

class OrderImportForm(forms.Form):
    PERIOD_CHOICES = [
        ('1_day', 'Останній день'),
        ('7_days', 'Останній тиждень'),
        ('30_days', 'Останній місяць'),
        ('all', 'Всі замовлення'),
        ('test', 'Тестовий імпорт (10 останніх)'),
    ]
    period = forms.ChoiceField(choices=PERIOD_CHOICES, label="Виберіть період для імпорту")

class OrderFullImportForm(forms.Form):
    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label="Дата початку")
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label="Дата завершення")

class OrderFilterForm(forms.Form):
    order_id = forms.IntegerField(required=False, label="ID замовлення")
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}), label="Дата створення (від)")
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}), label="Дата створення (до)")
    client_first_name = forms.CharField(required=False, label="Ім'я клієнта")
    client_last_name = forms.CharField(required=False, label="Прізвище клієнта")
    phone = forms.CharField(required=False, label="Телефон")
    email = forms.CharField(required=False, label="Email")
    status_name = forms.CharField(required=False, label="Статус")
    source = forms.CharField(required=False, label="Джерело")
    # Додаємо поле для фільтрації за магазинами
    stores = forms.ModelMultipleChoiceField(
        queryset=Store.objects.none(),
        required=False,
        label="Магазини",
        widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(OrderFilterForm, self).__init__(*args, **kwargs)
        if user:
            self.fields['stores'].queryset = user.stores.all()

class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ['store_name', 'api_key']
        labels = {
            'store_name': 'Назва магазину',
            'api_key': 'API ключ',
        }

class CommissionAnalyticsForm(forms.Form):
    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label="Дата початку")
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label="Дата завершення")
