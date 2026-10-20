from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.utils.uploads import get_uploads_root
from app.db.session import engine
from app.db.base import Base
from app.api.routers import auth_router, users_router, devices_router, leases_router, support_ticket_router, access_permission_router, device_events_router, warehouse_router, email_shedules_router
from app.core.logging_config import setup_logging
import app.models

setup_logging()

app = FastAPI(title="API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

uploads_dir = get_uploads_root()
uploads_dir.mkdir(parents=True, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(devices_router)
app.include_router(leases_router)
app.include_router(support_ticket_router)
app.include_router(access_permission_router)
app.include_router(device_events_router)
app.include_router(warehouse_router)
app.include_router(email_shedules_router)