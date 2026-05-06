"""
State utilities
"""

import uuid


def generate_agent_trace_id() -> str:
    """Generate a unique trace ID for agent execution"""
    return f"agent_{uuid.uuid4().hex[:12]}"
