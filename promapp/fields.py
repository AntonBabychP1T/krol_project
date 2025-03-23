from django.db import models
from cryptography.fernet import Fernet
from django.conf import settings

class EncryptedCharField(models.CharField):
    """
    Кастомне поле для зберігання зашифрованих рядкових даних за допомогою Fernet.
    Ключ шифрування має бути визначений у settings.ENCRYPTION_KEY.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(settings, 'ENCRYPTION_KEY'):
            raise Exception("ENCRYPTION_KEY не задано у налаштуваннях!")
        self.fernet = Fernet(settings.ENCRYPTION_KEY)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        try:
            return self.fernet.decrypt(value.encode()).decode()
        except Exception:
            return value

    def get_prep_value(self, value):
        if value is None:
            return value
        return self.fernet.encrypt(value.encode()).decode()
