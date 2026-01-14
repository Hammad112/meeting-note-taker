"""
Run script for Meeting Bot.
This script allows running the bot directly from the project root.
"""

import sys
import os

# Add the current directory to sys.path so we can import modules
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Now we can import and run the meeting bot
from main import run

if __name__ == "__main__":
    run()
