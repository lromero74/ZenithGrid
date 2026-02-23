"""Tests for app/services/portfolio_conversion_service.py"""

from datetime import datetime, timedelta

from app.services.portfolio_conversion_service import (
    get_task_progress,
    update_task_progress,
    cleanup_old_tasks,
    _conversion_tasks,
)


class TestGetTaskProgress:
    def setup_method(self):
        _conversion_tasks.clear()

    def test_returns_none_for_unknown_task(self):
        assert get_task_progress("nonexistent") is None

    def test_returns_existing_task(self):
        _conversion_tasks["test-1"] = {"task_id": "test-1", "status": "running"}
        result = get_task_progress("test-1")
        assert result["status"] == "running"


class TestUpdateTaskProgress:
    def setup_method(self):
        _conversion_tasks.clear()

    def test_creates_new_task_on_first_update(self):
        update_task_progress("task-1", total=10, status="running")
        task = _conversion_tasks["task-1"]
        assert task["total"] == 10
        assert task["status"] == "running"
        assert task["current"] == 0
        assert task["progress_pct"] == 0

    def test_updates_existing_task(self):
        update_task_progress("task-1", total=10)
        update_task_progress("task-1", current=5)
        task = _conversion_tasks["task-1"]
        assert task["current"] == 5
        assert task["progress_pct"] == 50

    def test_progress_percentage_calculation(self):
        update_task_progress("task-1", total=4, current=1)
        assert _conversion_tasks["task-1"]["progress_pct"] == 25

        update_task_progress("task-1", current=4)
        assert _conversion_tasks["task-1"]["progress_pct"] == 100

    def test_zero_total_gives_zero_progress(self):
        update_task_progress("task-1")
        assert _conversion_tasks["task-1"]["progress_pct"] == 0

    def test_completed_status_sets_completed_at(self):
        update_task_progress("task-1", status="completed")
        assert _conversion_tasks["task-1"]["completed_at"] is not None

    def test_failed_status_sets_completed_at(self):
        update_task_progress("task-1", status="failed")
        assert _conversion_tasks["task-1"]["completed_at"] is not None

    def test_running_status_no_completed_at(self):
        update_task_progress("task-1", status="running")
        assert _conversion_tasks["task-1"]["completed_at"] is None

    def test_updates_sold_and_failed_counts(self):
        update_task_progress("task-1", sold_count=3, failed_count=1)
        task = _conversion_tasks["task-1"]
        assert task["sold_count"] == 3
        assert task["failed_count"] == 1

    def test_updates_errors_list(self):
        update_task_progress("task-1", errors=["error 1", "error 2"])
        assert _conversion_tasks["task-1"]["errors"] == ["error 1", "error 2"]

    def test_updates_message(self):
        update_task_progress("task-1", message="Processing ETH-BTC")
        assert _conversion_tasks["task-1"]["message"] == "Processing ETH-BTC"


class TestCleanupOldTasks:
    def setup_method(self):
        _conversion_tasks.clear()

    def test_removes_completed_tasks_older_than_1_hour(self):
        old_time = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        _conversion_tasks["old-task"] = {
            "task_id": "old-task",
            "completed_at": old_time,
        }
        cleanup_old_tasks()
        assert "old-task" not in _conversion_tasks

    def test_keeps_recent_completed_tasks(self):
        recent_time = datetime.utcnow().isoformat()
        _conversion_tasks["recent-task"] = {
            "task_id": "recent-task",
            "completed_at": recent_time,
        }
        cleanup_old_tasks()
        assert "recent-task" in _conversion_tasks

    def test_keeps_running_tasks(self):
        _conversion_tasks["running-task"] = {
            "task_id": "running-task",
            "completed_at": None,
        }
        cleanup_old_tasks()
        assert "running-task" in _conversion_tasks

    def test_empty_tasks_dict(self):
        cleanup_old_tasks()  # Should not raise
