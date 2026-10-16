from app.api.routers.auth import router as auth_router
from app.api.routers.users import router as users_router
from app.api.routers.devices import router as devices_router
from app.api.routers.lease import router as leases_router
from app.api.routers.support_ticket import router as support_ticket_router
from app.api.routers.access_permission import router as access_permission_router
from app.api.routers.device_events import router as device_events_router
from app.api.routers.warehouse import router as warehouse_router
from app.api.routers.email_schedules import router as email_shedules_router

__all__ = [
    "auth_router",
    "users_router",
    "devices_router",
    "leases_router",
    "support_ticket_router",
    "access_permission_router",
    "device_events_router",
    "warehouse_router",
    "email_shedules_router",
]