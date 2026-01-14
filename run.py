"""
Run script for Meeting Bot.
This script allows running the bot directly from within the meeting_bot directory.
"""

import sys
import os

# Add the parent directory to sys.path so we can import meeting_bot as a package
parent_dir = os.path.dirname(os.path.abspath(__file__))
grandparent_dir = os.path.dirname(parent_dir)
if grandparent_dir not in sys.path:
    sys.path.insert(0, grandparent_dir)

# Now we can import and run the meeting bot
from meeting_bot.main import run

if __name__ == "__main__":
    run()
