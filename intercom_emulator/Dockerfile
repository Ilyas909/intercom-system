FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код эмулятора
COPY intercom.py .

# Запускаем эмулятор
CMD ["python", "-u", "intercom.py"]