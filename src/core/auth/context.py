from __future__ import annotations

from contextvars import ContextVar

current_account_id: ContextVar[int | None] = ContextVar("current_account_id", default=None)
current_account_role: ContextVar[str] = ContextVar("current_account_role", default="user")


def get_current_account_id() -> int | None:
    return current_account_id.get()


def get_current_role() -> str:
    return current_account_role.get()
