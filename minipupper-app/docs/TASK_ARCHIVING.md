# Task Archiving System

**Last Updated:** 2026-05-11

## Overview

When the TaskWatcher announces a completed task result to the user, the task is
archived to external storage. The active `tasks.json` file is cleaned up by the
Gateway cron which removes announced+completed tasks, keeping the file clean
for monitoring.

## Architecture

### Components

1. **TaskArchiver** (`src/core/task_archiver.py`)
   - Manages archiving of completed tasks
   - Stores tasks in date-partitioned archive files
   - Maintains an archive index for quick lookups
   - **Non-destructive** — does NOT remove from active `tasks.json`

2. **TaskWatcher** (`src/core/task_watcher.py`)
   - Polls `tasks.json` every 2s for completed tasks
   - Detects via `status: "completed"` AND `announced: false`
   - Generates Gemini-powered TTS announcement
   - Sets `announced: true` after TTS finishes
   - Archives for history (non-destructive)

3. **Gateway Cron** (every 5s)
   - Finds announced+completed tasks
   - Archives them via `TaskArchiver.archive_task()`
   - Removes from active `tasks.json`

4. **Archive Management CLI** (`scripts/manage_archives.py`)
   - Query and inspect archived tasks
   - Export archive data
   - Clean up old archives

## Why Non-Destructive Archive?

The initial implementation used `archive_and_remove()` which deleted the task
from `tasks.json` immediately after archiving. This caused a **race condition**
when the Gateway cron was simultaneously writing progress updates to the same
file — one write would overwrite the other, losing data.

The fix: the TaskWatcher only sets `announced: true` (a single field update)
and archives. The Gateway cron then cleans up later. Since the cron only
processes "pending" tasks, it never writes to a task that's already completed,
eliminating the race.

## Workflow

```
1. Task created:   tasks.json → { status: "pending", announced: false }
2. Gateway processes → { status: "completed", result: "...", announced: false }
3. TaskWatcher detects → announces via TTS → { announced: true }
4. TaskWatcher archives → archive file ← (non-destructive)
5. Cron cleanup → removes from tasks.json, archived copy remains
```

## File Structure

```
~/minipupper-app/
├── tasks.json                 # Active tasks (auto-cleaned)
├── tasks_archive.json         # Archive index (metadata)
└── tasks_archive/
    ├── 2026-05-11.json       # Tasks from May 11
    └── ...
```

## Archiver API

```python
from src.core.task_archiver import TaskArchiver

archiver = TaskArchiver()

# Archive a task (non-destructive — doesn't touch tasks.json)
archiver.archive_task(task)

# Get statistics
stats = archiver.get_archive_stats()

# Clean up old archives
archiver.cleanup_old_archives(days_to_keep=30)
```

## CLI Tool

```bash
cd ~/minipupper-app/scripts

# View statistics
python manage_archives.py stats

# Show recent tasks
python manage_archives.py recent --limit 20

# List by action
python manage_archives.py list --action "web_search"

# Export all as JSON
python manage_archives.py export --format json > backup.json

# Clean up old archives
python manage_archives.py cleanup --days 30
```
