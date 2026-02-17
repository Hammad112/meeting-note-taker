#!/bin/bash
# startup.sh - Initialize PulseAudio and start the application
# This script sets up a virtual audio sink for browser audio capture

echo "=== Meeting Bot Startup Script ==="

# Start PulseAudio daemon if not running
if ! pulseaudio --check 2>/dev/null; then
    echo "Starting PulseAudio daemon..."
    pulseaudio --start --log-target=syslog --exit-idle-time=-1 2>/dev/null || true
    sleep 1
fi

# Create virtual audio sink for capturing browser audio
echo "Setting up virtual audio sink..."
if pactl list sinks short 2>/dev/null | grep -q "vsink"; then
    echo "Virtual sink 'vsink' already exists"
else
    # Load null sink module (creates a virtual output device)
    pactl load-module module-null-sink sink_name=vsink sink_properties=device.description="VirtualSink" 2>/dev/null || true
fi

# Set the virtual sink as default
pactl set-default-sink vsink 2>/dev/null || true

# Export environment variables for the application
export PULSE_SINK="vsink"
export PULSE_SOURCE="vsink.monitor"

echo "PulseAudio ready. Default sink: vsink"
echo "Audio capture source: vsink.monitor"

# Start Xvfb in background
echo "Starting Xvfb..."
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
sleep 1

echo "Starting uvicorn..."
# Run uvicorn directly (not through xvfb-run) with DISPLAY already set
exec python -u -m uvicorn main:app --host 0.0.0.0 --port 8888
