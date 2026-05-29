from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


def new_id() -> str:
    """Create ids in one place so model defaults stay consistent."""
    return str(uuid4())


def utc_now() -> datetime:
    """Use timezone-aware UTC timestamps throughout runtime models."""
    return datetime.now(UTC)
