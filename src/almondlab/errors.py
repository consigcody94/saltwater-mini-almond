"""Structured AlmondLab errors and a concise raising helper."""

from typing import Never


class AlmondLabError(Exception):
    """An error with machine-readable, structured context."""

    def __init__(
        self,
        code: str,
        message: str,
        field_path: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.field_path = field_path
        self.details = details

    def to_dict(self) -> dict[str, object]:
        serialized: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "field_path": self.field_path,
        }
        if self.details is not None:
            serialized["details"] = self.details
        return serialized


def fail(
    code: str,
    message: str,
    field_path: str,
    details: dict[str, object] | None = None,
) -> Never:
    """Raise a structured AlmondLab error with stable fields."""
    raise AlmondLabError(code, message, field_path, details)
