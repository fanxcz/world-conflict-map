import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import auth, conflicts, events, importer, map_timeline, misc
from app.config import get_settings
from app.database import init_db
from app.importer.scheduler import start_scheduler

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("wcm")

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_per_minute}/minute"])


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    start_scheduler()
    yield


app = FastAPI(
    title="World Conflict Map API",
    version="1.0.0",
    description="Independent information GIS platform for documented conflicts.",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda r, e: JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"}),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_and_headers(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled error %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    elapsed = (time.time() - start) * 1000
    logger.info("%s %s -> %s (%.1fms)", request.method, request.url.path, response.status_code, elapsed)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def root():
    return {"name": "World Conflict Map API", "version": "1.0.0", "docs": "/docs"}


app.include_router(auth.router, prefix="/api")
app.include_router(conflicts.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(importer.router, prefix="/api")
app.include_router(misc.router_misc, prefix="/api")
app.include_router(map_timeline.router, prefix="/api")
