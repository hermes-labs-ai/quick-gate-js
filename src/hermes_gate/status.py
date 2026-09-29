from __future__ import annotations

from enum import StrEnum


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    REVIEW_UNAVAILABLE = "REVIEW_UNAVAILABLE"
    PARKED = "PARKED"
    ERROR = "ERROR"


EXIT_CODES = {
    Status.PASS: 0,
    Status.NOT_APPLICABLE: 0,
    Status.FAIL: 1,
    Status.NOT_CONFIGURED: 2,
    Status.ERROR: 2,
    Status.REVIEW_UNAVAILABLE: 3,
    Status.PARKED: 3,
}
