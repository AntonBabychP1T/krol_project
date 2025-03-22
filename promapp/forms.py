from django import forms

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
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Дата початку"
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Дата завершення"
    )

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
