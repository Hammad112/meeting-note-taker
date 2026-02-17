#!/bin/bash
# Generate a simple black avatar image for the bot
# This creates a 640x480 black PNG image

convert -size 640x480 xc:black /app/assets/avatar.png 2>/dev/null || \
python3 -c "
from PIL import Image
img = Image.new('RGB', (640, 480), color='black')
img.save('/app/assets/avatar.png')
" 2>/dev/null || \
echo "Could not generate avatar image"
