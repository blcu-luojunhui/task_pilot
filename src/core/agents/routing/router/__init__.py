"""
Task router for pre-loop complexity assessment and decomposition.

Uses the same planner to decide whether a goal is simple or should be split
into sub-goals before the main loop executes.
"""

from .router import TaskRouter

__all__ = ["TaskRouter"]
