FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    SCRAPER_OUTPUT_FILE=/app/data/output/recipes.tsv \
    SCRAPER_STATE_DIR=/app/state

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libgbm1 \
    libgtk-3-0 \
    libnotify4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip uv && uv pip install --system .
RUN python -m playwright install --with-deps chromium

COPY . .
RUN mkdir -p /app/data /app/state

ENTRYPOINT ["python", "-m", "src.main"]
