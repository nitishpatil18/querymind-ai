from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import Container, get_container
from app.database.inspector import RelationshipInfo, SchemaInfo, TableInfo
from app.rag.document_generator import render_table_document
from app.schemas.request import RefreshRequest
from app.services.schema_service import SchemaStatus

router = APIRouter(prefix="/api/schema", tags=["schema"])


class TableDetail(BaseModel):
    table: TableInfo
    document: str
    relationships: list[RelationshipInfo]


@router.get("", response_model=SchemaInfo, summary="Discovered database schema")
def get_schema(c: Container = Depends(get_container)) -> SchemaInfo:
    return c.schema_service.get_schema()


@router.get("/status", response_model=SchemaStatus, summary="Schema index status")
def schema_status(c: Container = Depends(get_container)) -> SchemaStatus:
    return c.schema_service.status()


@router.post("/refresh", response_model=SchemaStatus, summary="Re-inspect the database and rebuild the vector index")
def refresh_schema(body: RefreshRequest | None = None, c: Container = Depends(get_container)) -> SchemaStatus:
    return c.schema_service.refresh(reindex=(body.reindex if body else True))


@router.get("/tables/{table_name}", response_model=TableDetail, summary="Details of one table")
def get_table(table_name: str, c: Container = Depends(get_container)) -> TableDetail:
    table = c.schema_service.get_table(table_name)
    schema = c.schema_service.get_schema()
    rels = [r for r in schema.relationships if table.name in (r.child_table, r.parent_table)]
    return TableDetail(table=table, document=render_table_document(table, schema), relationships=rels)
