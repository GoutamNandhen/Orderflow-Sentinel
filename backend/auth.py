"""Operator credentials are private runtime configuration, never source defaults."""

import os
import secrets
from .db import DATA


def operator_password():
    configured = os.getenv("OPERATOR_PASSWORD")
    if configured:
        return configured
    if os.getenv("ENVIRONMENT") == "production":
        raise RuntimeError(
            "Production requires OPERATOR_PASSWORD in the private hosting environment"
        )
    private_file = DATA / "operator-password.local"
    try:
        descriptor = os.open(private_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return private_file.read_text(encoding="utf-8").strip()
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(secrets.token_urlsafe(32))
    return private_file.read_text(encoding="utf-8").strip()
