"""
Prompting module - Prompt 工程组件

包含：
- assembler: 动态 Prompt 组装器
- knowledge_selector: 知识选择器
"""

from .assembler import PromptAssembler
from .knowledge_selector import KnowledgeSelector

__all__ = [
    "PromptAssembler",
    "KnowledgeSelector",
]
