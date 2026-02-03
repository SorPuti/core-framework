"""
Ready-to-use authentication ViewSets.

Provides common auth endpoints out of the box:
- POST /auth/register - User registration
- POST /auth/login - User login
- POST /auth/refresh - Token refresh
- GET /auth/me - Current user info
- POST /auth/logout - Logout (optional)
- POST /auth/change-password - Change password

Example:
    from core.auth.views import CoreAuthViewSet
    from myapp.models import User
    
    class AuthViewSet(CoreAuthViewSet):
        user_model = User
    
    # Register routes
    router.register_viewset("/auth", AuthViewSet, basename="auth")
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from fastapi import Request, HTTPException

from core.views import ViewSet, action
from core.permissions import AllowAny, IsAuthenticated
from core.auth.tokens import create_access_token, create_refresh_token, verify_token
from core.auth.schemas import (
    BaseRegisterInput,
    BaseLoginInput,
    RefreshTokenInput,
    ChangePasswordInput,
    TokenResponse,
    BaseUserOutput,
    MessageResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class CoreAuthViewSet(ViewSet):
    """
    Ready-to-use authentication ViewSet.
    
    Provides standard auth endpoints. Configure by setting class attributes:
    
    Attributes:
        user_model: Your User model class (required)
        register_schema: Custom registration schema (optional)
        login_schema: Custom login schema (optional)
        user_output_schema: Custom user output schema (optional)
        access_token_expire_minutes: Token expiration (default: 30)
        refresh_token_expire_days: Refresh token expiration (default: 7)
    
    Example:
        from core.auth.views import CoreAuthViewSet
        from myapp.models import User
        from myapp.schemas import RegisterInput, UserOutput
        
        class AuthViewSet(CoreAuthViewSet):
            user_model = User
            register_schema = RegisterInput  # Optional custom schema
            user_output_schema = UserOutput  # Optional custom output
        
        router.register_viewset("/auth", AuthViewSet, basename="auth")
    
    Endpoints created:
        POST /auth/register - Register new user
        POST /auth/login - Login and get tokens
        POST /auth/refresh - Refresh access token
        GET /auth/me - Get current user
        POST /auth/change-password - Change password
    """
    
    # Configuration - override in subclass
    user_model: type | None = None
    register_schema: type = BaseRegisterInput
    login_schema: type = BaseLoginInput
    user_output_schema: type = BaseUserOutput
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # ViewSet config
    tags: list[str] = ["auth"]
    
    def _get_user_model(self):
        """Get user model or raise error."""
        if self.user_model is None:
            raise NotImplementedError(
                "CoreAuthViewSet requires user_model to be set. "
                "Example:\n"
                "class AuthViewSet(CoreAuthViewSet):\n"
                "    user_model = User"
            )
        return self.user_model
    
    def _create_tokens(self, user) -> dict:
        """Create access and refresh tokens for user."""
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email},
            expires_minutes=self.access_token_expire_minutes,
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user.id)},
            expires_days=self.refresh_token_expire_days,
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire_minutes * 60,
        }
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def register(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict:
        """
        Register a new user.
        
        Returns tokens on successful registration.
        """
        User = self._get_user_model()
        
        # Validate input
        validated = self.register_schema.model_validate(data)
        
        # Check if user exists
        existing = await User.get_by_email(validated.email, db)
        if existing:
            raise HTTPException(
                status_code=400,
                detail="User with this email already exists"
            )
        
        # Create user
        user = await User.create_user(
            email=validated.email,
            password=validated.password,
            db=db,
        )
        
        # Commit the transaction
        await db.commit()
        
        # Return tokens
        return self._create_tokens(user)
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def login(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict:
        """
        Login with email and password.
        
        Returns access and refresh tokens.
        """
        User = self._get_user_model()
        
        # Validate input
        validated = self.login_schema.model_validate(data)
        
        # Authenticate
        user = await User.authenticate(
            email=validated.email,
            password=validated.password,
            db=db,
        )
        
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )
        
        # Commit any changes (last_login update)
        await db.commit()
        
        # Return tokens
        return self._create_tokens(user)
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def refresh(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict:
        """
        Refresh access token using refresh token.
        """
        User = self._get_user_model()
        
        # Validate input
        validated = RefreshTokenInput.model_validate(data)
        
        # Verify refresh token
        payload = verify_token(validated.refresh_token, token_type="refresh")
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired refresh token"
            )
        
        # Get user
        user_id = payload.get("sub")
        user = await User.objects.using(db).filter(id=int(user_id)).first()
        
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=401,
                detail="User not found or inactive"
            )
        
        # Return new tokens
        return self._create_tokens(user)
    
    @action(methods=["GET"], detail=False, permission_classes=[IsAuthenticated])
    async def me(
        self,
        request: Request,
        db: "AsyncSession",
        **kwargs,
    ) -> dict:
        """
        Get current authenticated user.
        """
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated"
            )
        
        return self.user_output_schema.model_validate(user).model_dump()
    
    @action(methods=["POST"], detail=False, permission_classes=[IsAuthenticated])
    async def change_password(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict:
        """
        Change password for current user.
        """
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated"
            )
        
        # Validate input
        validated = ChangePasswordInput.model_validate(data)
        
        # Verify current password
        if not user.check_password(validated.current_password):
            raise HTTPException(
                status_code=400,
                detail="Current password is incorrect"
            )
        
        # Set new password
        user.set_password(validated.new_password)
        await user.save(db)
        await db.commit()
        
        return {"message": "Password changed successfully", "success": True}


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "CoreAuthViewSet",
]
