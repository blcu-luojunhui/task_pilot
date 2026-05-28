from .context import current_account_id, get_current_account_id, current_account_role, get_current_role
from .token import generate_token, hash_password, verify_password, verify_password_with_legacy, generate_salt
from .repository import AccountRepository, TokenRepository, UsageRepository
from .service import AuthService, DuplicateError, UnauthorizedError
from .middleware import AuthMiddleware
from .decorators import public, require_role

__all__ = [
    "current_account_id",
    "get_current_account_id",
    "current_account_role",
    "get_current_role",
    "generate_token",
    "hash_password",
    "verify_password",
    "verify_password_with_legacy",
    "generate_salt",
    "AccountRepository",
    "TokenRepository",
    "UsageRepository",
    "AuthService",
    "DuplicateError",
    "UnauthorizedError",
    "AuthMiddleware",
    "public",
    "require_role",
]
