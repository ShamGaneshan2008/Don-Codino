"""Redact known secrets before persistence or presentation."""

import re

SENSITIVE_KEY = r"(?:api[_-]?key|password|secret|token)"


def redact(value: str, secret: str = "") -> str:
    if secret:
        value = value.replace(secret, "[REDACTED]")
    value = re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
        "[REDACTED PRIVATE KEY]",
        value,
        flags=re.DOTALL,
    )
    value = re.sub(r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{8,}", "[REDACTED]", value)
    value = re.sub(r"(?i)(bearer\s+)[\w.\-]+", r"\1[REDACTED]", value)

    def assignment(match):
        original = match.group(2)
        quote = original[0] if original[0] in {"'", '"'} else ""
        return match.group(1) + quote + "[REDACTED]" + quote

    return re.sub(
        rf"""(?i)(["']?\b{SENSITIVE_KEY}["']?\s*[=:]\s*)"""
        r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;}]+)""",
        assignment,
        value,
    )


def sanitize(value, secret: str = ""):
    """Redact string values without corrupting structured JSON reports."""
    if isinstance(value, str):
        return redact(value, secret)
    if isinstance(value, list):
        return [sanitize(item, secret) for item in value]
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if re.fullmatch(SENSITIVE_KEY, key, re.IGNORECASE)
            else sanitize(item, secret)
            for key, item in value.items()
        }
    return value
