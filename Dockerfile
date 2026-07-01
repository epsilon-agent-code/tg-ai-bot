FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY bot.py .
COPY public_bot.py .
COPY generate_session.py .
COPY start.sh .

# Делаем скрипт исполняемым
RUN chmod +x start.sh

# Запускаем через bash
CMD ["bash", "start.sh"]