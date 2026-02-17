# syntax=docker/dockerfile:1

FROM python:3.11-slim

# Python runtime settings
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install system dependencies with Playwright deps in one layer
RUN apt-get update && apt-get install -y \
    xvfb \
    xauth \
    ffmpeg \
    pulseaudio \
    pulseaudio-utils \
    alsa-utils \
    imagemagick \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Create assets directory and generate a black avatar image (fallback for fake camera)
RUN mkdir -p /app/assets && \
    convert -size 640x480 xc:'#1e1e1e' /app/assets/avatar.png && \
    echo "Generated avatar.png"


# Copy requirements first for Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers with system deps
RUN playwright install --with-deps chromium

# Copy the rest of the application
COPY . .

# Make startup script executable
RUN chmod +x startup.sh

EXPOSE 8888

# Use startup script that initializes PulseAudio before starting the app
CMD ["./startup.sh"]
