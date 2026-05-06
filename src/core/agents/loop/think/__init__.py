"""
Think stage for the agent loop.

Think prepares a dynamic system prompt, compacts context if needed, sets streaming context, and asks the planner for the next assistant message.
"""

from .thinker import AssistantPlanner, Think
from .prompt_assembler import PromptAssembler

__all__ = ["AssistantPlanner", "Think", "PromptAssembler"]
