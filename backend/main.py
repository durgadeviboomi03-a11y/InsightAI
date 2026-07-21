"""
backend/main.py

Entry point for the InsightAI FastAPI application.

Responsibilities:
- Create and configure the FastAPI app instance
- Register CORS middleware
- Configure structured logging
- Register all API routers (auth, users, datasets, chat, reports, forecast, admin)
- Define startup/shutdown lifecycle events
- Expose a root health-check endpoint
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.config import get_settings
from backend.database import Base, engine

# NOTE: Route modules below will be created in upcoming files.
# Each import is added here as soon as its corresponding route file exists.
# from backend.routes import auth_routes
# from backend.routes import user_routes
# from backend.routes import dataset_routes
# from backend.routes import chat_routes
# from backend.routes import report_routes
# from backend.routes import forecast_routes
# from backend.routes import admin_routes

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.

    Runs startup logic before the app begins accepting requests,
    and shutdown/cleanup logic after the app stops.
    """
    logger.info("Starting InsightAI backend...")

    # Create all database tables if they don't already exist.
    # In production, prefer Alembic migrations over this call.
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created.")

    yield  # Application runs while control is here

    logger.info("Shutting down InsightAI backend...")


def create_app() -> FastAPI:
    """
    Application factory. Creates and configures the FastAPI instance.

    Using a factory function (rather than a bare module-level app)
    makes the app easier to test and reuse across different entry points.
    """
    app = FastAPI(
        title="InsightAI - AI-Powered Data Analyst",
        description="A full-stack SaaS platform for automated data analysis, "
        "visualization, AI chat, forecasting, and reporting.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ---------- CORS Middleware ----------
    # Allows the frontend (served from a different origin during development)
    # to communicate with this API.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------- Static Files ----------
    # Serves generated charts, uploaded previews, etc. if needed by the frontend.
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # ---------- Global Exception Handler ----------
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Catches any unhandled exception so the API never leaks raw tracebacks
        to clients, while still logging full details server-side for debugging.
        """
        logger.error(f"Unhandled exception on {request.method} {request.url}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred. Please try again later."},
        )

    # ---------- Routers ----------
    # Each router will be uncommented as its file is created in upcoming steps.
    # app.include_router(auth_routes.router, prefix="/api/auth", tags=["Authentication"])
    # app.include_router(user_routes.router, prefix="/api/users", tags=["Users"])
    # app.include_router(dataset_routes.router, prefix="/api/datasets", tags=["Datasets"])
    # app.include_router(chat_routes.router, prefix="/api/chat", tags=["AI Chat"])
    # app.include_router(report_routes.router, prefix="/api/reports", tags=["Reports"])
    # app.include_router(forecast_routes.router, prefix="/api/forecast", tags=["Forecasting"])
    # app.include_router(admin_routes.router, prefix="/api/admin", tags=["Admin"])

    # ---------- Health Check ----------
    @app.get("/", tags=["Health"])
    async def root() -> dict:
        """Basic health-check endpoint to confirm the API is running."""
        return {
            "status": "ok",
            "service": "InsightAI Backend",
            "version": "1.0.0",
        }

    return app


app = create_app()