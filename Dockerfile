# Dockerfile
FROM python:3.9-slim

# Забороняємо запис .pyc файлів та встановлюємо буферизацію
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Встановлюємо робочу директорію
WORKDIR /code

# Копіюємо файл із залежностями та встановлюємо їх
COPY requirements.txt /code/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копіюємо весь проєкт
COPY . /code/

# Запускаємо застосунок за допомогою Gunicorn
CMD ["gunicorn", "myproject.wsgi:application", "--bind", "0.0.0.0:8000"]
