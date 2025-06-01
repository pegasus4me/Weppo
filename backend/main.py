import os
import sys
from pathlib import Path

# Add the project root directory to Python path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from fastapi import FastAPI, Request, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from backend.apis.agent import router as agent_router, initialize_agent as initialize_agent_module
from backend.apis.support import router as support_router
from dotenv import load_dotenv
import logging
from contextlib import asynccontextmanager

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO, # Default log level
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
    handlers=[
        logging.StreamHandler() # Log to console
        # You can add logging.FileHandler("app.log") here for file logging
    ]
)
logger = logging.getLogger(__name__)
# --- End Logging Configuration ---

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# --- Rate Limiting (using slowapi) ---
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"]) # Example: 60 requests per minute
# --- End Rate Limiting ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI app startup: Initializing agent...")
    initialize_agent_module()
    logger.info("FastAPI app startup: Agent initialized.")
    yield
    logger.info("FastAPI app shutdown: Cleaning up resources...")

app = FastAPI(title="Backend API", lifespan=lifespan)

# --- Register Rate Limiter ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# --- End Register Rate Limiter ---

# --- Global Exception Handlers ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error for request {request.method} {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation Error", "errors": exc.errors()},
    )

# Ensure HTTPException handler from FastAPI is not overridden by a generic one if not intended.
# FastAPI's default HTTPException handling is usually sufficient.
# This custom one is fine if you want specific logging or response format for all HTTPErrors.
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTP exception for request {request.method} {request.url}: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}, # exc.detail might already be a dict/list, ensure it's serializable
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.critical(f"Unhandled exception for request {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error", "error_message": str(exc)},
    )
# --- End Global Exception Handlers ---

# Apply rate limiting to routers
app.include_router(agent_router, prefix="/api/agent", tags=["Agent"], dependencies=[Depends(limiter.limit("30/minute"))])
app.include_router(support_router, prefix="/api/support", tags=["Support"], dependencies=[Depends(limiter.limit("60/minute"))])


@app.get("/")
@limiter.limit("100/minute") # Specific limit for the root endpoint
async def read_root(request: Request): # Add request: Request for limiter context
    logger.info("Root endpoint '/' accessed.")
    return {"message": "Welcome to the Backend API"}

# Placeholder for other app configurations (middleware, etc.)
