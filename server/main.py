import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.routers.analytics import router as analytics_router
from server.routers.status import router as status_router
from server.routers.upload import router as upload_router
from server.state import server_state
from storage.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("parqueame.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Parqueame Smart Parking Server...")
    Path("storage/images").mkdir(parents=True, exist_ok=True)
    init_db()
    server_state.initialize(config_dir="config/cameras")
    logger.info("Server initialization complete. Listening for incoming camera frames.")
    yield
    logger.info("Shutting down Parqueame Server.")


app = FastAPI(
    title="Parqueame Smart Parking API",
    description="Real-time parking lot occupancy detection and camera ingestion hub",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend integration (Vite dev server, localhost, and LAN IPs)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file serving for rolling annotated camera images
Path("storage/images").mkdir(parents=True, exist_ok=True)
app.mount("/storage/images", StaticFiles(directory="storage/images"), name="images")

# Register routers
app.include_router(upload_router)
app.include_router(status_router)
app.include_router(analytics_router)


@app.get("/", tags=["General"])
def root():
    """Welcome endpoint providing documentation links and server status."""
    return {
        "project": "Parqueame Smart Parking API",
        "version": "1.0.0",
        "status": "online",
        "docs_url": "/docs",
        "health_url": "/api/v1/health",
        "status_url": "/api/v1/status",
    }


if __name__ == "__main__":
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
