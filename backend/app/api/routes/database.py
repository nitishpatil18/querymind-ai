from fastapi import APIRouter, Depends

from app.api.deps import Container, get_container
from app.database.connection import DatabaseStatus, check_connection

router = APIRouter(prefix="/api/database", tags=["database"])


@router.get("/status", response_model=DatabaseStatus, summary="PostgreSQL connection status")
def database_status(c: Container = Depends(get_container)) -> DatabaseStatus:
    return check_connection(c.engine, c.settings)
