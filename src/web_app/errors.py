"""Stable domain errors exposed through the web API contract."""

class SafeFailure(RuntimeError):
    """A guarded turn could not be committed; authoritative State remains unchanged."""
