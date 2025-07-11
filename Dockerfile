FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create storage directory
RUN mkdir -p storage/rss/config storage/rss/sitemaps

CMD ["python", "site-bot.py"]