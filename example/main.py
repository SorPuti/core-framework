"""Event tracking and marketing analytics platform."""

from core import APIView, AutoRouter, CoreApp
from core.auth import configure_auth
from core.datetime import configure_datetime
from core.permissions import AllowAny
from example.models import User
from example.settings import settings

configure_datetime(
    default_timezone="UTC",
    use_aware_datetimes=True,
)

configure_auth(
    secret_key=settings.secret_key,
    access_token_expire_minutes=settings.auth_access_token_expire_minutes,
    refresh_token_expire_days=settings.auth_refresh_token_expire_days,
    password_hasher="bcrypt",
    user_model=User,
)


class HealthView(APIView):
    """Health check endpoint for monitoring."""

    permission_classes = [AllowAny]
    tags = ["Health"]

    async def get(self, request, **kwargs):
        return {
            "status": "healthy",
            "version": "0.1.0",
            "environment": settings.environment,
        }


class RootView(APIView):
    """Root endpoint with API information."""

    permission_classes = [AllowAny]
    tags = ["Root"]

    async def get(self, request, **kwargs):
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "docs": "/docs",
            "redoc": "/redoc",
        }


root_router = AutoRouter(prefix="", tags=["System"])

app = CoreApp(
    title="SimpleTrack API",
    description="Event tracking and marketing analytics platform.",
    version="0.1.0",
    settings=settings,
    routers=[root_router],
    middleware=["auth"],
)

app.add_api_route("/", RootView.as_route("/")[1], methods=["GET"], tags=["System"])
app.add_api_route("/health", HealthView.as_route("/health")[1], methods=["GET"], tags=["System"])
