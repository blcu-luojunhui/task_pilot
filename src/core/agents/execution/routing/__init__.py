"""
Agent Routing - Task Router

This module handles task routing and distribution:
- Task classification
- Route selection
- Load balancing
"""

from .router import TaskRouter

__all__ = [
    "TaskRouter",
]
