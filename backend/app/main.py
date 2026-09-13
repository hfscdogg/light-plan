import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.logging_setup import configure_logging
from app.models.database import create_tables
from app.routers import estimates, exports, plans, projects

# Before anything can log: uvicorn leaves the root logger unconfigured, so
# without this the app's own messages never reach the host's log stream.
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.log_storage_location()
    create_tables()
    os.makedirs(settings.upload_dir, exist_ok=True)
    # Mount upload directory now that it exists
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
    yield


app = FastAPI(
    title="LightPlan API",
    description="Proactive lighting layout tool for residential builders",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Basic auth middleware (only active if credentials are configured)
if settings.basic_auth_user and settings.basic_auth_pass:
    security = HTTPBasic()

    @app.middleware("http")
    async def basic_auth_middleware(request: Request, call_next):
        # Skip auth for health check
        if request.url.path == "/api/health":
            return await call_next(request)

        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Basic "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Basic"},
            )

        import base64

        try:
            decoded = base64.b64decode(auth.split(" ")[1]).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid credentials"},
                headers={"WWW-Authenticate": "Basic"},
            )

        correct_user = secrets.compare_digest(username, settings.basic_auth_user)
        correct_pass = secrets.compare_digest(password, settings.basic_auth_pass)
        if not (correct_user and correct_pass):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid credentials"},
                headers={"WWW-Authenticate": "Basic"},
            )

        return await call_next(request)


# Include routers
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(plans.router, prefix="/api/projects", tags=["plans"])
app.include_router(estimates.router, prefix="/api/projects", tags=["estimates"])
app.include_router(exports.router, prefix="/api/exports", tags=["exports"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


# Serve frontend static build if it exists (single-service deployment)
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

# The plan viewer is the product: it is what the sales team uses, what
# Livewire links to, and the only page with AI room detection and the
# draggable fixture overlay. It answers on "/" so the bare domain is the
# thing to hand a builder. The older React uploader stays at /classic.
PRODUCTION_PAGE = "preview.html"
LEGACY_PATH = "classic"


def resolve_static_path(frontend_dir: str, full_path: str) -> str | None:
    """Pick the file to serve for a non-API request.

    Returns None when the path escapes ``frontend_dir``, so a traversal
    attempt is a 404 rather than a file read outside the build directory.
    """
    index = os.path.join(frontend_dir, "index.html")
    production = os.path.join(frontend_dir, PRODUCTION_PAGE)

    if full_path in ("", "index.html"):
        # Fall back to the SPA when the viewer is not in this build.
        return production if os.path.isfile(production) else index
    if full_path.strip("/") == LEGACY_PATH:
        return index

    candidate = os.path.realpath(os.path.join(frontend_dir, full_path))
    root = os.path.realpath(frontend_dir)
    if candidate != root and not candidate.startswith(root + os.sep):
        return None
    if os.path.isfile(candidate):
        return candidate
    return index  # unknown route: let the SPA router handle it


if os.path.isdir(_frontend_dir):
    from fastapi.responses import FileResponse

    # Serve static assets (JS, CSS, etc.)
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dir, "assets")), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        path = resolve_static_path(_frontend_dir, full_path)
        if path is None:
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(path)
