class ChatEventType:
    TOKEN_DELTA = "chat.token_delta"
    TOOL_CALL_START = "chat.tool_call_start"
    TOOL_CALL_END = "chat.tool_call_end"
    TURN_END = "chat.turn_end"
    TURN_ERROR = "chat.turn_error"


__all__ = ["ChatEventType"]
