"""
Data factories for generating test data.

Provides a factory pattern for creating test instances with fake data.

Usage:
    # Define a factory
    class UserFactory(Factory):
        model = User
        
        @classmethod
        def build(cls, **overrides):
            return {
                "email": fake.email(),
                "name": fake.name(),
                **overrides,
            }
    
    # Use in tests
    async def test_user_creation(db):
        user = await UserFactory.create(db)
        assert user.id is not None
        
        users = await UserFactory.create_batch(db, 5)
        assert len(users) == 5
"""

from __future__ import annotations

import logging
from typing import TypeVar, Generic, Any, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("core.testing")

# Try to import faker, provide fallback
try:
    from faker import Faker
    fake = Faker()
except ImportError:
    # Minimal fake data generator if faker not installed
    class MinimalFaker:
        """Minimal faker replacement when faker is not installed."""
        
        _counter = 0
        
        def email(self) -> str:
            self._counter += 1
            return f"user{self._counter}@example.com"
        
        def name(self) -> str:
            self._counter += 1
            return f"User {self._counter}"
        
        def first_name(self) -> str:
            return "John"
        
        def last_name(self) -> str:
            return "Doe"
        
        def text(self, max_nb_chars: int = 200) -> str:
            return "Lorem ipsum dolor sit amet." * (max_nb_chars // 30 + 1)
        
        def sentence(self) -> str:
            return "This is a test sentence."
        
        def paragraph(self) -> str:
            return "This is a test paragraph with multiple sentences. It contains some text for testing purposes."
        
        def url(self) -> str:
            self._counter += 1
            return f"https://example.com/{self._counter}"
        
        def uuid4(self) -> str:
            return str(uuid4())
        
        def random_int(self, min: int = 0, max: int = 9999) -> int:
            import random
            return random.randint(min, max)
        
        def boolean(self) -> bool:
            import random
            return random.choice([True, False])
        
        def date_this_year(self) -> str:
            from datetime import date
            return date.today().isoformat()
        
        def date_time_this_year(self):
            from datetime import datetime
            return datetime.now()
        
        def company(self) -> str:
            self._counter += 1
            return f"Company {self._counter}"
        
        def phone_number(self) -> str:
            self._counter += 1
            return f"+1-555-{self._counter:04d}"
        
        def address(self) -> str:
            return "123 Test Street, Test City, TC 12345"
    
    fake = MinimalFaker()
    logger.warning(
        "faker not installed. Using minimal fake data generator. "
        "Install with: pip install faker"
    )


T = TypeVar("T")


class Factory(Generic[T]):
    """
    Base factory for creating test instances.
    
    Subclass this to create factories for your models.
    
    Example:
        class UserFactory(Factory):
            model = User
            
            @classmethod
            def build(cls, **overrides):
                return {
                    "email": fake.email(),
                    "name": fake.name(),
                    "is_active": True,
                    **overrides,
                }
        
        # Build dict (no database)
        data = UserFactory.build(name="Custom Name")
        
        # Create instance (saves to database)
        user = await UserFactory.create(db)
        
        # Create multiple
        users = await UserFactory.create_batch(db, 10)
    
    Attributes:
        model: The model class to create instances of
    """
    
    model: type[T]
    
    @classmethod
    def build(cls, **overrides) -> dict[str, Any]:
        """
        Build a dict of attributes without saving.
        
        Override this method in subclasses to define default values.
        
        Args:
            **overrides: Values to override defaults
            
        Returns:
            Dict of model attributes
        """
        raise NotImplementedError(
            f"{cls.__name__} must implement build() method"
        )
    
    @classmethod
    async def create(
        cls,
        db: "AsyncSession",
        **overrides,
    ) -> T:
        """
        Create and save an instance to the database.
        
        Args:
            db: Database session
            **overrides: Values to override defaults
            
        Returns:
            Created model instance
        """
        data = cls.build(**overrides)
        instance = cls.model(**data)
        
        db.add(instance)
        await db.commit()
        await db.refresh(instance)
        
        logger.debug(f"Factory created: {cls.model.__name__}")
        return instance
    
    @classmethod
    async def create_batch(
        cls,
        db: "AsyncSession",
        count: int,
        **overrides,
    ) -> list[T]:
        """
        Create multiple instances.
        
        Args:
            db: Database session
            count: Number of instances to create
            **overrides: Values to override defaults for all instances
            
        Returns:
            List of created instances
        """
        instances = []
        for _ in range(count):
            instance = await cls.create(db, **overrides)
            instances.append(instance)
        
        logger.debug(f"Factory created batch: {count} x {cls.model.__name__}")
        return instances
    
    @classmethod
    def build_batch(cls, count: int, **overrides) -> list[dict[str, Any]]:
        """
        Build multiple dicts without saving.
        
        Args:
            count: Number of dicts to build
            **overrides: Values to override defaults
            
        Returns:
            List of dicts
        """
        return [cls.build(**overrides) for _ in range(count)]


class UserFactory(Factory):
    """
    Factory for creating test users.
    
    Works with AbstractUser-based models.
    
    Example:
        # Create user with random data
        user = await UserFactory.create(db)
        
        # Create with specific email
        admin = await UserFactory.create(db, email="admin@example.com", is_superuser=True)
        
        # Create batch
        users = await UserFactory.create_batch(db, 10)
    """
    
    model: type = None  # Set dynamically
    _default_password: str = "TestPass123!"
    
    @classmethod
    def _get_model(cls):
        """Get user model from auth config."""
        if cls.model is not None:
            return cls.model
        
        try:
            from core.auth.models import get_user_model
            return get_user_model()
        except Exception:
            pass
        
        try:
            from core.auth.models import AbstractUser
            return AbstractUser
        except Exception:
            raise RuntimeError(
                "Could not determine User model. "
                "Set UserFactory.model = YourUserModel"
            )
    
    @classmethod
    def build(cls, **overrides) -> dict[str, Any]:
        """Build user data dict."""
        password = overrides.pop("password", cls._default_password)
        
        data = {
            "email": fake.email(),
            "is_active": True,
            "is_superuser": False,
            "is_staff": False,
        }
        data.update(overrides)
        
        # Handle password hashing
        if "password_hash" not in data:
            try:
                from core.auth.hashers import get_hasher
                hasher = get_hasher()
                data["password_hash"] = hasher.hash(password)
            except Exception:
                # Fallback: assume model handles password
                data["_password"] = password
        
        return data
    
    @classmethod
    async def create(
        cls,
        db: "AsyncSession",
        **overrides,
    ) -> Any:
        """Create and save a user."""
        model = cls._get_model()
        
        data = cls.build(**overrides)
        
        # Handle password separately if model has set_password
        password = data.pop("_password", None)
        
        instance = model(**data)
        
        if password and hasattr(instance, "set_password"):
            instance.set_password(password)
        
        db.add(instance)
        await db.commit()
        await db.refresh(instance)
        
        return instance


# Additional common factories

class SequenceFactory:
    """
    Generate sequential values for unique fields.
    
    Example:
        seq = SequenceFactory("user_{n}@example.com")
        seq.next()  # "user_1@example.com"
        seq.next()  # "user_2@example.com"
    """
    
    def __init__(self, template: str, start: int = 1) -> None:
        """
        Initialize sequence.
        
        Args:
            template: String template with {n} placeholder
            start: Starting number
        """
        self.template = template
        self.counter = start
    
    def next(self) -> str:
        """Get next value in sequence."""
        value = self.template.format(n=self.counter)
        self.counter += 1
        return value
    
    def reset(self, start: int = 1) -> None:
        """Reset counter."""
        self.counter = start


class LazyAttribute:
    """
    Lazily compute attribute value.
    
    Example:
        class PostFactory(Factory):
            model = Post
            
            @classmethod
            def build(cls, **overrides):
                return {
                    "title": fake.sentence(),
                    "slug": LazyAttribute(lambda obj: slugify(obj["title"])),
                    **overrides,
                }
    """
    
    def __init__(self, func) -> None:
        self.func = func
    
    def __call__(self, obj: dict) -> Any:
        return self.func(obj)


def resolve_lazy_attributes(data: dict) -> dict:
    """Resolve any LazyAttribute values in a dict."""
    result = {}
    for key, value in data.items():
        if isinstance(value, LazyAttribute):
            result[key] = value(data)
        else:
            result[key] = value
    return result
