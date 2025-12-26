"""
Portfolio conversion service with progress tracking
"""
import asyncio
import logging
from typing import Dict, Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# In-memory storage for conversion progress
# Key: task_id, Value: progress dict
_conversion_tasks: Dict[str, Dict] = {}


def get_task_progress(task_id: str) -> Optional[Dict]:
    """Get progress for a conversion task"""
    return _conversion_tasks.get(task_id)


def update_task_progress(
    task_id: str,
    total: int = None,
    current: int = None,
    status: str = None,
    message: str = None,
    sold_count: int = None,
    failed_count: int = None,
    errors: List[str] = None,
):
    """Update progress for a conversion task"""
    if task_id not in _conversion_tasks:
        _conversion_tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "total": 0,
            "current": 0,
            "sold_count": 0,
            "failed_count": 0,
            "errors": [],
            "message": "",
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
        }
    
    task = _conversion_tasks[task_id]
    
    if total is not None:
        task["total"] = total
    if current is not None:
        task["current"] = current
    if status is not None:
        task["status"] = status
    if message is not None:
        task["message"] = message
    if sold_count is not None:
        task["sold_count"] = sold_count
    if failed_count is not None:
        task["failed_count"] = failed_count
    if errors is not None:
        task["errors"] = errors
    
    if status == "completed" or status == "failed":
        task["completed_at"] = datetime.utcnow().isoformat()
    
    # Calculate progress percentage
    if task["total"] > 0:
        task["progress_pct"] = int((task["current"] / task["total"]) * 100)
    else:
        task["progress_pct"] = 0


def cleanup_old_tasks():
    """Clean up tasks older than 1 hour"""
    from datetime import datetime, timedelta
    
    cutoff = datetime.utcnow() - timedelta(hours=1)
    to_remove = []
    
    for task_id, task in _conversion_tasks.items():
        if task.get("completed_at"):
            completed = datetime.fromisoformat(task["completed_at"])
            if completed < cutoff:
                to_remove.append(task_id)
    
    for task_id in to_remove:
        del _conversion_tasks[task_id]
        logger.info(f"Cleaned up old conversion task: {task_id}")
