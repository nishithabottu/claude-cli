"""Example Pydantic schemas for use with `claude-cli --schema`.

Used in the README walkthrough and the success-metric eval. Keep this file at
the repo root so users can run `claude-cli --schema schemas.RootCause` from
anywhere they cloned the project.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class RootCause(BaseModel):
    """Structured root-cause extraction from a single log line."""

    severity: Severity = Field(
        description="How serious the issue is, on a 4-level scale."
    )
    service: str = Field(
        description="Which service or component emitted the log (e.g. 'auth-api', 'redis')."
    )
    summary: str = Field(
        description="One-sentence plain-English description of what went wrong."
    )
    likely_cause: str = Field(
        description="Most probable root cause based on the log line."
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Verbatim substrings from the log that support the diagnosis.",
    )
    error_code: Optional[str] = Field(
        default=None,
        description="Numeric or symbolic error code if present (e.g. '500', 'ECONNREFUSED').",
    )
