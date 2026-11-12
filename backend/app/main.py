"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import acquisitions, analysis, audit, auth, cases, devices, health, reports
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import init_db
from app.serial.transport import SerialTransportError


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "app://."],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(SerialTransportError)
    async def serial_error_handler(_request: Request, exc: SerialTransportError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    prefix = settings.api_v1_prefix
    app.include_router(health.router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(cases.router, prefix=prefix)
    app.include_router(devices.router, prefix=prefix)
    app.include_router(acquisitions.router, prefix=prefix)
    app.include_router(analysis.router, prefix=prefix)
    app.include_router(reports.router, prefix=prefix)
    app.include_router(audit.router, prefix=prefix)

    return app


app = create_app()

