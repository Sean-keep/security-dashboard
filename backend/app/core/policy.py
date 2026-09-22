"""
Password policy — shared by user management and self-service password change.
"""
import re

from app.core.config import settings


def validate_password_strength(password: str) -> None:
    """Raise ValueError when the password does not meet policy.

    Policy: at least ``settings.PASSWORD_MIN_LENGTH`` characters, with at
    least one letter and one digit. Placeholders are rejected outright.
    """
    if not isinstance(password, str) or not password:
        raise ValueError("密码不能为空")

    min_len = settings.PASSWORD_MIN_LENGTH
    if len(password) < min_len:
        raise ValueError(f"密码长度至少 {min_len} 位")

    if not re.search(r"[A-Za-z]", password):
        raise ValueError("密码必须包含字母")
    if not re.search(r"\d", password):
        raise ValueError("密码必须包含数字")

    banned = {"password", "12345678", "123456789", "admin123", "qwertyui", "changeme"}
    if password.lower() in banned:
        raise ValueError("密码过于常见，请更换")
