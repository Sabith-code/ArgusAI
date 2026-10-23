import os
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import check_connection
from api.routes import router

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler verifying MongoDB connectivity on server startup."""
    logger.info("Initializing FastAPI application...")
    connected, version, err = check_connection()
    if connected:
        logger.info(f"Connected to MongoDB server version {version}.")
    else:
        logger.warning(f"MongoDB connection check failed on startup: {err}")
    yield
    logger.info("FastAPI application shutdown complete.")

app = FastAPI(
    title="Brand Reputation Monitoring System API",
    description="Production-grade read-only REST API exposing mentions, event clusters, historical metrics, anomalies, and risk scorecards.",
    version="1.0.0",
    lifespan=lifespan
)

# Configurable CORS Middleware
cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
allowed_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],  # Strictly Read-Only HTTP methods
    allow_headers=["*"]
)

app.include_router(router)
