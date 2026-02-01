"""
Testes para o sistema de Serializers.
"""

import pytest
from pydantic import ValidationError, field_validator

from core.serializers import InputSchema, OutputSchema


class UserInput(InputSchema):
    """Schema de teste para input."""
    
    email: str
    name: str
    age: int
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email format")
        return v.lower()
    
    @field_validator("age")
    @classmethod
    def validate_age(cls, v: int) -> int:
        if v < 0 or v > 150:
            raise ValueError("Age must be between 0 and 150")
        return v


class UserOutput(OutputSchema):
    """Schema de teste para output."""
    
    id: int
    email: str
    name: str


def test_input_schema_valid():
    """Testa validação de input válido."""
    data = {
        "email": "Test@Example.com",
        "name": "Test User",
        "age": 25,
    }
    
    validated = UserInput.model_validate(data)
    
    assert validated.email == "test@example.com"  # Lowercase
    assert validated.name == "Test User"
    assert validated.age == 25


def test_input_schema_invalid_email():
    """Testa validação de email inválido."""
    data = {
        "email": "invalid-email",
        "name": "Test User",
        "age": 25,
    }
    
    with pytest.raises(ValidationError) as exc_info:
        UserInput.model_validate(data)
    
    assert "Invalid email format" in str(exc_info.value)


def test_input_schema_invalid_age():
    """Testa validação de idade inválida."""
    data = {
        "email": "test@example.com",
        "name": "Test User",
        "age": 200,
    }
    
    with pytest.raises(ValidationError) as exc_info:
        UserInput.model_validate(data)
    
    assert "Age must be between 0 and 150" in str(exc_info.value)


def test_input_schema_missing_field():
    """Testa validação com campo faltando."""
    data = {
        "email": "test@example.com",
        "name": "Test User",
        # age missing
    }
    
    with pytest.raises(ValidationError):
        UserInput.model_validate(data)


def test_input_schema_extra_field_forbidden():
    """Testa que campos extras são rejeitados."""
    data = {
        "email": "test@example.com",
        "name": "Test User",
        "age": 25,
        "extra_field": "should fail",
    }
    
    with pytest.raises(ValidationError):
        UserInput.model_validate(data)


def test_output_schema_from_dict():
    """Testa criação de output schema de dicionário."""
    data = {
        "id": 1,
        "email": "test@example.com",
        "name": "Test User",
    }
    
    output = UserOutput.model_validate(data)
    
    assert output.id == 1
    assert output.email == "test@example.com"
    assert output.name == "Test User"


def test_output_schema_to_dict():
    """Testa conversão de output schema para dicionário."""
    output = UserOutput(
        id=1,
        email="test@example.com",
        name="Test User",
    )
    
    data = output.model_dump()
    
    assert data == {
        "id": 1,
        "email": "test@example.com",
        "name": "Test User",
    }


class MockUser:
    """Mock de objeto ORM."""
    
    def __init__(self):
        self.id = 1
        self.email = "test@example.com"
        self.name = "Test User"


def test_output_schema_from_orm():
    """Testa criação de output schema de objeto ORM."""
    user = MockUser()
    
    output = UserOutput.model_validate(user)
    
    assert output.id == 1
    assert output.email == "test@example.com"
    assert output.name == "Test User"


def test_output_schema_from_orm_list():
    """Testa criação de lista de output schemas."""
    users = [MockUser(), MockUser()]
    users[1].id = 2
    users[1].email = "test2@example.com"
    
    outputs = UserOutput.from_orm_list(users)
    
    assert len(outputs) == 2
    assert outputs[0].id == 1
    assert outputs[1].id == 2
