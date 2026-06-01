"""Domain models for Todo App."""

from enum import StrEnum


class Priority(StrEnum):
    """Priority level for a todo item."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
