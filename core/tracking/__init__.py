"""
Run tracking and history module.

Part 3 requirement: Track execution status for operational autonomy.
"""

from .run_tracker import RunTracker, get_last_run, get_run_history

__all__ = ["RunTracker", "get_last_run", "get_run_history"]
