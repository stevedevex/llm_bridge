"""bridge-kit's validators. Each returns findings; an error stops the caller (exit code 1)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Finding:
    severity: str  # error | warning | info
    check: str  # which rule, e.g. "coverage", "if-missing"
    message: str
    file: str
    line: int | None = None
    row: str | None = None

    def __str__(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        row = f" row {self.row}" if self.row else ""
        return f"{self.severity.upper():7} {where}{row} [{self.check}] {self.message}"
