FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create storage directory
RUN mkdir -p storage/rss/config storage/rss/sitemaps

# Define build arguments
ARG TELEGRAM_BOT_TOKEN
ARG TELEGRAM_TARGET_CHAT

# Set environment variables
ENV TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
ENV TELEGRAM_TARGET_CHAT=${TELEGRAM_TARGET_CHAT}

CMD ["python", "site-bot.py"]