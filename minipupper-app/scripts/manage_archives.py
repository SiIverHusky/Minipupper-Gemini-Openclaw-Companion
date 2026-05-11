#!/usr/bin/env python3
"""
Task Archive Management Utility

Provides CLI commands to:
- View archive statistics
- Query archived tasks
- Clean up old archives
- Export archive data
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.task_archiver import TaskArchiver, ARCHIVE_DIR, ARCHIVE_INDEX


def print_stats(archiver):
    """Print archive statistics."""
    stats = archiver.get_archive_stats()
    
    print("\n=== Task Archive Statistics ===")
    print(f"Total archived tasks: {stats.get('total_archived', 0)}")
    
    if stats.get('status_counts'):
        print("\nTasks by status:")
        for status, count in stats['status_counts'].items():
            print(f"  {status}: {count}")
    
    if stats.get('date_counts'):
        print("\nTasks by date:")
        for date, count in sorted(stats['date_counts'].items()):
            print(f"  {date}: {count}")
    
    print(f"\nArchive directory: {stats.get('archive_directory')}")
    print(f"Archive index: {stats.get('archive_index_file')}")
    print()


def print_recent(archiver, limit=10):
    """Print recently archived tasks."""
    try:
        index = archiver._load_archive_index()
        
        # Sort by archive time (most recent first)
        sorted_tasks = sorted(
            index.items(),
            key=lambda x: x[1].get('archivedAt', 0),
            reverse=True
        )[:limit]
        
        print(f"\n=== Most Recent {limit} Archived Tasks ===")
        for task_id, entry in sorted_tasks:
            archived_at = entry.get('archivedAt', 0)
            action = entry.get('action', 'unknown')
            status = entry.get('status', 'unknown')
            
            time_str = datetime.fromtimestamp(archived_at).strftime("%Y-%m-%d %H:%M:%S")
            print(f"{task_id[:16]:20} | {action:30} | {status:10} | {time_str}")
        print()
        
    except Exception as e:
        print(f"Error reading archive index: {e}")


def list_by_action(archiver, action_filter=None):
    """List archived tasks filtered by action."""
    try:
        index = archiver._load_archive_index()
        
        if action_filter:
            filtered = {k: v for k, v in index.items() 
                       if action_filter.lower() in v.get('action', '').lower()}
            print(f"\n=== Tasks for action: {action_filter} ===")
        else:
            filtered = index
            print("\n=== All Archived Tasks by Action ===")
        
        # Group by action
        by_action = {}
        for task_id, entry in filtered.items():
            action = entry.get('action', 'unknown')
            if action not in by_action:
                by_action[action] = []
            by_action[action].append(task_id)
        
        for action in sorted(by_action.keys()):
            task_ids = by_action[action]
            print(f"\n{action}: {len(task_ids)} tasks")
            for task_id in task_ids[:5]:  # Show first 5
                print(f"  {task_id[:16]}")
            if len(task_ids) > 5:
                print(f"  ... and {len(task_ids) - 5} more")
        print()
        
    except Exception as e:
        print(f"Error reading archive index: {e}")


def export_archive(archiver, format='json', date=None):
    """Export archive data."""
    try:
        if date:
            # Export specific date
            archive_file = archiver._get_archive_file_for_date(
                datetime.strptime(date, "%Y-%m-%d").timestamp()
            )
            if not os.path.exists(archive_file):
                print(f"No archive found for date: {date}")
                return
            
            tasks = archiver._load_archive_file(archive_file)
            print(f"\n=== Archive for {date} ({len(tasks)} tasks) ===\n")
        else:
            # Export all
            index = archiver._load_archive_index()
            print(f"\n=== All Archived Tasks ({len(index)} total) ===\n")
            
            # Could also export individual date files
            all_tasks = {}
            for date_file in Path(ARCHIVE_DIR).glob("*.json"):
                date_tasks = archiver._load_archive_file(str(date_file))
                all_tasks.update(date_tasks)
            tasks = all_tasks
        
        if format == 'json':
            print(json.dumps(tasks, indent=2))
        else:  # csv
            import csv
            writer = csv.DictWriter(
                sys.stdout,
                fieldnames=['taskId', 'action', 'status', 'createdAt', 'updatedAt']
            )
            writer.writeheader()
            for task_id, task in sorted(tasks.items()):
                writer.writerow({
                    'taskId': task_id,
                    'action': task.get('action', ''),
                    'status': task.get('status', ''),
                    'createdAt': task.get('createdAt', ''),
                    'updatedAt': task.get('updatedAt', ''),
                })
        
    except Exception as e:
        print(f"Error exporting archive: {e}")


def cleanup(archiver, days=30, force=False):
    """Clean up old archives."""
    if not force:
        print(f"This will delete tasks archived more than {days} days ago.")
        response = input("Continue? (y/N) ")
        if response.lower() != 'y':
            print("Cancelled.")
            return
    
    removed = archiver.cleanup_old_archives(days_to_keep=days)
    print(f"Removed {removed} archived tasks older than {days} days.")
    
    # Show updated stats
    stats = archiver.get_archive_stats()
    print(f"Remaining archived tasks: {stats.get('total_archived', 0)}")


def main():
    parser = argparse.ArgumentParser(
        description='Task Archive Management Utility',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View archive statistics
  python manage_archives.py stats
  
  # Show 20 most recent tasks
  python manage_archives.py recent --limit 20
  
  # List tasks for specific action
  python manage_archives.py list --action "robot.move"
  
  # Export all archived tasks as JSON
  python manage_archives.py export --format json > backup.json
  
  # Export specific date
  python manage_archives.py export --date 2026-05-11
  
  # Clean up tasks older than 60 days
  python manage_archives.py cleanup --days 60 --force
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Stats command
    subparsers.add_parser('stats', help='Show archive statistics')
    
    # Recent command
    recent_parser = subparsers.add_parser('recent', help='Show recently archived tasks')
    recent_parser.add_argument('--limit', type=int, default=10,
                              help='Number of tasks to show (default: 10)')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List tasks by action')
    list_parser.add_argument('--action', help='Filter by action name')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export archived tasks')
    export_parser.add_argument('--format', choices=['json', 'csv'], default='json',
                              help='Export format (default: json)')
    export_parser.add_argument('--date', help='Export specific date (YYYY-MM-DD)')
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old archives')
    cleanup_parser.add_argument('--days', type=int, default=30,
                               help='Keep tasks from last N days (default: 30)')
    cleanup_parser.add_argument('--force', action='store_true',
                               help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    archiver = TaskArchiver()
    
    if args.command == 'stats':
        print_stats(archiver)
    elif args.command == 'recent':
        print_recent(archiver, limit=args.limit)
    elif args.command == 'list':
        list_by_action(archiver, action_filter=args.action)
    elif args.command == 'export':
        export_archive(archiver, format=args.format, date=args.date)
    elif args.command == 'cleanup':
        cleanup(archiver, days=args.days, force=args.force)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
