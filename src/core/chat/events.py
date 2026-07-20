class ChatEventType:
    TOKEN_DELTA = "token_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    TURN_END = "turn_end"
    TURN_ERROR = "turn_error"


__all__ = ["ChatEventType"]
