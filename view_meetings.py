#!/usr/bin/env python3
"""
Meeting Database Viewer

Simple script to view and query the meeting database.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))


def format_datetime(iso_string):
    """Format ISO datetime string for display."""
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return iso_string


def view_database():
    """View the meeting database."""
    db_path = Path("data/meeting_database.json")
    
    if not db_path.exists():
        print("❌ Meeting database not found at data/meeting_database.json")
        print("   The database will be created automatically after your first meeting.")
        return
    
    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            db = json.load(f)
    except Exception as e:
        print(f"❌ Error reading database: {e}")
        return
    
    print("=" * 80)
    print("📊 MEETING DATABASE")
    print("=" * 80)
    print(f"Created: {format_datetime(db.get('created_at', 'Unknown'))}")
    print(f"Last Updated: {format_datetime(db.get('last_updated', 'Unknown'))}")
    print(f"Total Meetings: {len(db.get('meetings', {}))}")
    print("=" * 80)
    
    meetings = db.get('meetings', {})
    
    if not meetings:
        print("\n📭 No meetings in database yet.")
        print("   Meetings will be added automatically after they end.")
        return
    
    print("\n📋 MEETINGS:\n")
    
    for i, (meeting_url, entry) in enumerate(meetings.items(), 1):
        print(f"{i}. Meeting URL:")
        print(f"   {meeting_url}")
        print(f"\n   S3 Path:")
        print(f"   {entry.get('s3_path', 'N/A')}")
        print(f"\n   Added: {format_datetime(entry.get('added_at', 'Unknown'))}")
        
        metadata = entry.get('metadata', {})
        if metadata:
            print(f"\n   Details:")
            if 'meeting_id' in metadata:
                print(f"   - Meeting ID: {metadata['meeting_id']}")
            if 'title' in metadata:
                print(f"   - Title: {metadata['title']}")
            if 'platform' in metadata:
                print(f"   - Platform: {metadata['platform']}")
            if 'export_timestamp' in metadata:
                print(f"   - Exported: {format_datetime(metadata['export_timestamp'])}")
        
        print("\n" + "-" * 80 + "\n")


def search_meeting(url_fragment):
    """Search for meetings by URL fragment."""
    db_path = Path("data/meeting_database.json")
    
    if not db_path.exists():
        print("❌ Meeting database not found")
        return
    
    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            db = json.load(f)
    except Exception as e:
        print(f"❌ Error reading database: {e}")
        return
    
    meetings = db.get('meetings', {})
    matches = []
    
    for url, entry in meetings.items():
        if url_fragment.lower() in url.lower():
            matches.append((url, entry))
    
    if not matches:
        print(f"❌ No meetings found matching: {url_fragment}")
        return
    
    print(f"\n✅ Found {len(matches)} meeting(s):\n")
    
    for i, (meeting_url, entry) in enumerate(matches, 1):
        print(f"{i}. {meeting_url}")
        print(f"   S3: {entry.get('s3_path', 'N/A')}")
        metadata = entry.get('metadata', {})
        if metadata.get('title'):
            print(f"   Title: {metadata['title']}")
        print()


def show_stats():
    """Show database statistics."""
    db_path = Path("data/meeting_database.json")
    
    if not db_path.exists():
        print("❌ Meeting database not found")
        return
    
    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            db = json.load(f)
    except Exception as e:
        print(f"❌ Error reading database: {e}")
        return
    
    meetings = db.get('meetings', {})
    
    # Count by platform
    platforms = {}
    for entry in meetings.values():
        platform = entry.get('metadata', {}).get('platform', 'unknown')
        platforms[platform] = platforms.get(platform, 0) + 1
    
    print("\n📊 STATISTICS\n")
    print(f"Total Meetings: {len(meetings)}")
    print("\nBy Platform:")
    for platform, count in sorted(platforms.items()):
        print(f"  - {platform}: {count}")
    
    # Check S3 uploads
    s3_count = sum(1 for entry in meetings.values() if entry.get('s3_path', '').startswith('s3://'))
    local_count = len(meetings) - s3_count
    
    print("\nStorage:")
    print(f"  - S3 Uploads: {s3_count}")
    print(f"  - Local Only: {local_count}")


def main():
    """Main CLI handler."""
    if len(sys.argv) == 1:
        view_database()
    elif sys.argv[1] == "search" and len(sys.argv) > 2:
        search_meeting(sys.argv[2])
    elif sys.argv[1] == "stats":
        show_stats()
    elif sys.argv[1] == "help":
        print("Meeting Database Viewer\n")
        print("Usage:")
        print("  python view_meetings.py           # View all meetings")
        print("  python view_meetings.py search <url>  # Search by URL fragment")
        print("  python view_meetings.py stats      # Show statistics")
        print("  python view_meetings.py help       # Show this help")
    else:
        print(f"Unknown command: {sys.argv[1]}")
        print("Run 'python view_meetings.py help' for usage information")


if __name__ == "__main__":
    main()
