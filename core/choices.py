"""
Django-style Choices for enums with value and display label.

Provides TextChoices and IntegerChoices classes that can be used
in models, serializers, and API documentation.

Example:
    from core.choices import TextChoices, IntegerChoices
    
    class Status(TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"
    
    class Priority(IntegerChoices):
        LOW = 1, "Low Priority"
        MEDIUM = 2, "Medium Priority"
        HIGH = 3, "High Priority"
    
    class Post(Model):
        status: Mapped[str] = Field.choice(Status, default=Status.DRAFT)
        priority: Mapped[int] = Field.choice(Priority, default=Priority.MEDIUM)
    
    # Access value and label
    Status.DRAFT.value      # "draft"
    Status.DRAFT.label      # "Draft"
    Status.choices          # [("draft", "Draft"), ("published", "Published"), ...]
    Status.values           # ["draft", "published", "archived"]
    Status.labels           # ["Draft", "Published", "Archived"]
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TypeVar, Generic


T = TypeVar("T")


class ChoicesMeta(type(Enum)):
    """
    Metaclass for Choices that handles the (value, label) tuple syntax.
    
    Allows defining choices as:
        DRAFT = "draft", "Draft"
    
    Instead of:
        DRAFT = "draft"
    
    Compatible with Python 3.11+ and 3.12+ using Django's approach.
    Labels are extracted after enum creation from member values.
    """
    
    def __new__(mcs, name: str, bases: tuple, namespace: dict, **kwargs):
        # Create the enum class
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        
        # Extract labels from members.
        # When TextChoices/IntegerChoices __new__ runs first, it stores
        # the explicit label in member._label_ (Issue #22 fix).
        # For raw Enum values that are tuples, we extract from _value_.
        labels = {}
        
        for member in cls:
            # Priority 1: label explicitly stored by __new__ (TextChoices/IntegerChoices)
            stored_label = getattr(member, '_label_', None)
            if stored_label is not None:
                labels[member.value] = stored_label
                continue
            
            # Priority 2: _value_ is still a tuple (plain Choices without custom __new__)
            value = member._value_
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                labels[value[0]] = value[1]
            else:
                # Fallback: auto-generate label from name
                labels[value] = member.name.replace("_", " ").title()
        
        cls._labels = labels
        return cls
    
    @property
    def choices(cls) -> list[tuple[Any, str]]:
        """
        Return list of (value, label) tuples.
        
        Useful for form fields, API documentation, etc.
        
        Example:
            Status.choices  # [("draft", "Draft"), ("published", "Published")]
        """
        return [(member.value, member.label) for member in cls]
    
    @property
    def values(cls) -> list[Any]:
        """
        Return list of all values.
        
        Example:
            Status.values  # ["draft", "published", "archived"]
        """
        return [member.value for member in cls]
    
    @property
    def labels(cls) -> list[str]:
        """
        Return list of all labels.
        
        Example:
            Status.labels  # ["Draft", "Published", "Archived"]
        """
        return [member.label for member in cls]
    
    @property
    def max_length(cls) -> int:
        """
        Return the maximum length of all values (for TextChoices).
        
        Useful for setting max_length on string columns.
        
        Example:
            Field.string(max_length=Status.max_length)
        """
        return max(len(str(v)) for v in cls.values) if cls.values else 0


class Choices(Enum, metaclass=ChoicesMeta):
    """
    Base class for choices with value and label support.
    
    Use TextChoices for string values and IntegerChoices for integer values.
    """
    
    @property
    def label(self) -> str:
        """
        Return the human-readable label for this choice.
        
        Example:
            Status.DRAFT.label  # "Draft"
        """
        return self.__class__._labels.get(self.value, self.name.replace("_", " ").title())
    
    @classmethod
    def from_value(cls, value: Any) -> "Choices | None":
        """
        Get choice member by value.
        
        Example:
            Status.from_value("draft")  # Status.DRAFT
        """
        for member in cls:
            if member.value == value:
                return member
        return None
    
    @classmethod
    def get_label(cls, value: Any) -> str | None:
        """
        Get label for a value without getting the member.
        
        Example:
            Status.get_label("draft")  # "Draft"
        """
        member = cls.from_value(value)
        return member.label if member else None
    
    @classmethod
    def is_valid(cls, value: Any) -> bool:
        """
        Check if a value is valid for this choices class.
        
        Example:
            Status.is_valid("draft")  # True
            Status.is_valid("invalid")  # False
        """
        return value in cls.values
    
    def __str__(self) -> str:
        """Return the value as string."""
        return str(self.value)
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"


class TextChoices(str, Choices):
    """
    Choices class for string values.
    
    Example:
        class Status(TextChoices):
            DRAFT = "draft", "Draft"
            PUBLISHED = "published", "Published"
            ARCHIVED = "archived", "Archived"
        
        # Usage
        Status.DRAFT.value  # "draft"
        Status.DRAFT.label  # "Draft"
        Status.choices      # [("draft", "Draft"), ...]
        
        # In model
        class Post(Model):
            status: Mapped[str] = Field.choice(Status, default=Status.DRAFT)
        
        # Comparison works with strings
        post.status == "draft"  # True
        post.status == Status.DRAFT  # True
    """
    
    def __new__(cls, value, label=None):
        """Create enum member, extracting value from tuple if needed."""
        if isinstance(value, (list, tuple)):
            label = value[1] if len(value) >= 2 else label
            value = value[0]
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj._label_ = label  # Store explicit label for ChoicesMeta (Issue #22)
        return obj
    
    def _generate_next_value_(name, start, count, last_values):
        """Auto-generate value from name (lowercase with underscores)."""
        return name.lower()


class IntegerChoices(int, Choices):
    """
    Choices class for integer values.
    
    Example:
        class Priority(IntegerChoices):
            LOW = 1, "Low Priority"
            MEDIUM = 2, "Medium Priority"
            HIGH = 3, "High Priority"
            CRITICAL = 4, "Critical"
        
        # Usage
        Priority.HIGH.value  # 3
        Priority.HIGH.label  # "High Priority"
        Priority.choices     # [(1, "Low Priority"), (2, "Medium Priority"), ...]
        
        # In model
        class Task(Model):
            priority: Mapped[int] = Field.choice(Priority, default=Priority.MEDIUM)
        
        # Comparison works with integers
        task.priority == 3  # True
        task.priority == Priority.HIGH  # True
    """
    
    def __new__(cls, value, label=None):
        """Create enum member, extracting value from tuple if needed."""
        if isinstance(value, (list, tuple)):
            label = value[1] if len(value) >= 2 else label
            value = value[0]
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj._label_ = label  # Store explicit label for ChoicesMeta (Issue #22)
        return obj
    
    def _generate_next_value_(name, start, count, last_values):
        """Auto-generate value (incrementing integer)."""
        return count + 1


# =============================================================================
# Common Choices (ready to use)
# =============================================================================

class CommonStatus(TextChoices):
    """Common status choices for general use."""
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    PENDING = "pending", "Pending"
    SUSPENDED = "suspended", "Suspended"


class PublishStatus(TextChoices):
    """Status choices for publishable content."""
    DRAFT = "draft", "Draft"
    PENDING_REVIEW = "pending_review", "Pending Review"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class OrderStatus(TextChoices):
    """Status choices for orders/transactions."""
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"


class PaymentStatus(TextChoices):
    """Status choices for payments."""
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"
    CANCELLED = "cancelled", "Cancelled"


class TaskPriority(IntegerChoices):
    """Priority choices for tasks."""
    LOW = 1, "Low"
    MEDIUM = 2, "Medium"
    HIGH = 3, "High"
    CRITICAL = 4, "Critical"


class Weekday(IntegerChoices):
    """Weekday choices (ISO 8601)."""
    MONDAY = 1, "Monday"
    TUESDAY = 2, "Tuesday"
    WEDNESDAY = 3, "Wednesday"
    THURSDAY = 4, "Thursday"
    FRIDAY = 5, "Friday"
    SATURDAY = 6, "Saturday"
    SUNDAY = 7, "Sunday"


class Month(IntegerChoices):
    """Month choices."""
    JANUARY = 1, "January"
    FEBRUARY = 2, "February"
    MARCH = 3, "March"
    APRIL = 4, "April"
    MAY = 5, "May"
    JUNE = 6, "June"
    JULY = 7, "July"
    AUGUST = 8, "August"
    SEPTEMBER = 9, "September"
    OCTOBER = 10, "October"
    NOVEMBER = 11, "November"
    DECEMBER = 12, "December"


class Gender(TextChoices):
    """Gender choices."""
    MALE = "M", "Male"
    FEMALE = "F", "Female"
    OTHER = "O", "Other"
    PREFER_NOT_TO_SAY = "N", "Prefer not to say"


class Visibility(TextChoices):
    """Visibility choices for content."""
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"
    UNLISTED = "unlisted", "Unlisted"
    MEMBERS_ONLY = "members", "Members Only"


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Base classes
    "Choices",
    "TextChoices",
    "IntegerChoices",
    # Common choices
    "CommonStatus",
    "PublishStatus",
    "OrderStatus",
    "PaymentStatus",
    "TaskPriority",
    "Weekday",
    "Month",
    "Gender",
    "Visibility",
]
