"""FastAPI dependency injectors for authentication and app state."""
import os
from fastapi import Header, HTTPException, Request

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "dev-admin-key")
WIDGET_TOKEN_SECRET = os.getenv("WIDGET_TOKEN_SECRET", "dev-widget-token")


async def require_admin_key(x_api_key: str = Header(..., alias="x-api-key")):
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin API key")


async def require_widget_token(x_widget_token: str = Header(..., alias="x-widget-token")):
    if x_widget_token != WIDGET_TOKEN_SECRET:
        raise HTTPException(status_code=401, detail="Invalid widget token")


def get_pipeline(request: Request):
    return request.app.state.pipeline
