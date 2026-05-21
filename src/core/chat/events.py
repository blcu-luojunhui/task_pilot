class ChatEventType:
    TOKEN_DELTA = "chat.token_delta"
    TOOL_CALL_START = "chat.tool_call_start"
    TOOL_CALL_END = "chat.tool_call_end"
    TOOL_CALL_PROPOSED = "chat.tool_call_proposed"
    TURN_PAUSED = "chat.turn_paused"
    TURN_END = "chat.turn_end"
    TURN_ERROR = "chat.turn_error"
    MODE_CHANGED = "chat.mode_changed"


__all__ = ["ChatEventType"]
