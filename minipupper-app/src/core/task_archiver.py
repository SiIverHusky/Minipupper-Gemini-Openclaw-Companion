"""
Task Archiver - Archive completed tasks for historical storage

Manages archiving of completed tasks from the active tasks.json file
to external storage. Supports future expiration policies.

Archive structure:
- tasks_archive.json: Current unified archive
- tasks_archive/<date>/ : Date-partitioned archives (future)

This allows:
- Keeping active task file clean and responsive
- Maintaining historical record for audit/debugging
- Future implementation of expiration policies by date
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Archive files
TASKS_FILE = os.path.expanduser("~/minipupper-app/tasks.json")
ARCHIVE_DIR = os.path.expanduser("~/minipupper-app/tasks_archive")
ARCHIVE_INDEX = os.path.expanduser("~/minipupper-app/tasks_archive.json")


class TaskArchiver:
    """Manages archiving of completed tasks to external storage."""

    def __init__(self):
        self._lock = threading.Lock()
        self._ensure_archive_dirs()

    def _ensure_archive_dirs(self):
        """Create archive directories if they don't exist."""
        os.makedirs(ARCHIVE_DIR, exist_ok=True)

    def _get_archive_file_for_date(self, task_date: Optional[float] = None) -> str:
        """
        Get the archive file path for a given date.
        
        Args:
            task_date: Unix timestamp (default: now)
            
        Returns:
            Path to date-partitioned archive file
        """
        if task_date is None:
            task_date = time.time()
        
        date_str = datetime.fromtimestamp(task_date).strftime("%Y-%m-%d")
        return os.path.join(ARCHIVE_DIR, f"{date_str}.json")

    def _load_archive_index(self) -> dict:
        """Load the archive index (metadata about all archived tasks)."""
        if not os.path.exists(ARCHIVE_INDEX):
            return {}
        try:
            with open(ARCHIVE_INDEX) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("TaskArchiver: could not read archive index: %s", e)
            return {}

    def _save_archive_index(self, index: dict):
        """Save the archive index."""
        with open(ARCHIVE_INDEX, "w") as f:
            json.dump(index, f, indent=2)

    def _load_archive_file(self, archive_file: str) -> dict:
        """Load tasks from a specific archive file."""
        if not os.path.exists(archive_file):
            return {}
        try:
            with open(archive_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("TaskArchiver: could not read archive file %s: %s",
                          archive_file, e)
            return {}

    def _save_archive_file(self, archive_file: str, tasks: dict):
        """Save tasks to a specific archive file."""
        os.makedirs(os.path.dirname(archive_file), exist_ok=True)
        with open(archive_file, "w") as f:
            json.dump(tasks, f, indent=2)

    def archive_task(self, task: dict) -> bool:
        """
        Archive a single completed task.
        
        Moves the task from active tasks.json to archive storage,
        indexed by the task's completion date.
        
        Args:
            task: Task dictionary to archive
            
        Returns:
            True if successful, False otherwise
        """
        if not task:
            return False

        task_id = task.get("taskId")
        if not task_id:
            logger.warning("TaskArchiver: cannot archive task without taskId")
            return False

        try:
            with self._lock:
                # Get the creation date for partitioning
                created_at = task.get("createdAt", time.time())
                archive_file = self._get_archive_file_for_date(created_at)

                # Load existing archive for this date
                archive_tasks = self._load_archive_file(archive_file)

                # Calculate execution time (updatedAt - createdAt)
                updated_at = task.get("updatedAt", created_at)
                execution_time_seconds = max(0, updated_at - created_at)

                # Add execution time to task
                task_with_execution_time = task.copy()
                task_with_execution_time["executionTime"] = execution_time_seconds

                # Add task to archive
                archive_tasks[task_id] = task_with_execution_time

                # Save updated archive
                self._save_archive_file(archive_file, archive_tasks)

                # Update archive index with metadata
                index = self._load_archive_index()
                index[task_id] = {
                    "taskId": task_id,
                    "action": task.get("action", ""),
                    "status": task.get("status", ""),
                    "archivedAt": time.time(),
                    "archiveFile": archive_file,
                    "createdAt": created_at,
                    "executionTime": execution_time_seconds,
                }
                self._save_archive_index(index)

                logger.info("TaskArchiver: archived task %s to %s",
                           task_id[:8], archive_file)
                return True

        except Exception as e:
            logger.error("TaskArchiver: failed to archive task %s: %s",
                        task_id, e)
            return False

    def archive_tasks(self, tasks: List[dict]) -> int:
        """
        Archive multiple completed tasks.
        
        Args:
            tasks: List of task dictionaries to archive
            
        Returns:
            Number of tasks successfully archived
        """
        archived_count = 0
        for task in tasks:
            if self.archive_task(task):
                archived_count += 1
        return archived_count

    def remove_task_from_active(self, task_id: str, tasks_file: str = TASKS_FILE) -> bool:
        """
        Remove a task from the active tasks file.
        
        Args:
            task_id: ID of task to remove
            tasks_file: Path to tasks.json
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._lock:
                if not os.path.exists(tasks_file):
                    return False

                with open(tasks_file) as f:
                    tasks = json.load(f)

                if task_id in tasks:
                    del tasks[task_id]
                    with open(tasks_file, "w") as f:
                        json.dump(tasks, f, indent=2)
                    logger.info("TaskArchiver: removed task %s from active file",
                               task_id[:8])
                    return True
                return False

        except Exception as e:
            logger.error("TaskArchiver: failed to remove task %s: %s",
                        task_id, e)
            return False

    def archive_and_remove(self, task: dict, tasks_file: str = TASKS_FILE) -> bool:
        """
        Archive a task and remove it from the active tasks file (atomic operation).
        
        Args:
            task: Task dictionary to archive
            tasks_file: Path to tasks.json
            
        Returns:
            True if both operations succeeded
        """
        task_id = task.get("taskId")
        
        # First archive, then remove (if archive fails, task stays in active)
        if self.archive_task(task):
            if self.remove_task_from_active(task_id, tasks_file):
                return True
            else:
                # Archive succeeded but removal failed - log this state
                logger.warning("TaskArchiver: archived task %s but failed to remove from active",
                              task_id[:8])
                return False
        return False

    def get_archive_stats(self) -> dict:
        """
        Get statistics about archived tasks.
        
        Returns:
            Dictionary with archive statistics
        """
        try:
            index = self._load_archive_index()
            
            # Count by status
            status_counts = {}
            for entry in index.values():
                status = entry.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # Count by date
            date_counts = {}
            for archive_file in Path(ARCHIVE_DIR).glob("*.json"):
                date_str = archive_file.stem
                tasks = self._load_archive_file(str(archive_file))
                date_counts[date_str] = len(tasks)
            
            return {
                "total_archived": len(index),
                "status_counts": status_counts,
                "date_counts": date_counts,
                "archive_index_file": ARCHIVE_INDEX,
                "archive_directory": ARCHIVE_DIR,
            }
        except Exception as e:
            logger.error("TaskArchiver: failed to get stats: %s", e)
            return {}

    def cleanup_old_archives(self, days_to_keep: int = 30) -> int:
        """
        Remove archived tasks older than specified days.
        
        This can be called periodically to implement expiration policy.
        Configure the number of days to keep via days_to_keep parameter.
        
        Args:
            days_to_keep: Number of days of archives to retain (default: 30)
            
        Returns:
            Number of tasks removed
        """
        cutoff_time = time.time() - (days_to_keep * 86400)
        removed_count = 0

        try:
            with self._lock:
                index = self._load_archive_index()
                tasks_to_remove = []

                # Find tasks older than cutoff
                for task_id, entry in index.items():
                    if entry.get("archivedAt", 0) < cutoff_time:
                        tasks_to_remove.append((task_id, entry))

                # Remove from archive files and index
                for task_id, entry in tasks_to_remove:
                    archive_file = entry.get("archiveFile")
                    if archive_file:
                        archive_tasks = self._load_archive_file(archive_file)
                        if task_id in archive_tasks:
                            del archive_tasks[task_id]
                            self._save_archive_file(archive_file, archive_tasks)
                            removed_count += 1

                    # Remove from index
                    del index[task_id]

                self._save_archive_index(index)
                logger.info("TaskArchiver: cleaned up %d archived tasks older than %d days",
                           removed_count, days_to_keep)

        except Exception as e:
            logger.error("TaskArchiver: cleanup failed: %s", e)

        return removed_count
