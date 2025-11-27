from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.db import get_db
from app.models import User, Document, Upload
from app.schemas import DocumentResponse, UploadWithStatusResponse
from app.auth import get_current_user
from typing import List, Union, Literal
from pydantic import BaseModel

router = APIRouter(prefix="/api/search", tags=["Search"])

class SearchResponse(BaseModel):
    documents: List[DocumentResponse]
    uploads: List[UploadWithStatusResponse]

@router.get("/", response_model=SearchResponse)
async def search(
    q: str,
    type: Literal["all", "documents", "uploads"] = "all",
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search for documents and uploads by title/filename"""
    if len(q) < 2:
        return {"documents": [], "uploads": []}
        
    search_term = f"%{q}%"
    
    docs = []
    uploads = []
    
    if type in ["all", "documents"]:
        doc_query = (
            select(Document)
            .where(
                Document.owner_id == current_user.id,
                Document.title.ilike(search_term)
            )
            .limit(limit)
        )
        doc_result = await db.execute(doc_query)
        docs = doc_result.scalars().all()
        
    if type in ["all", "uploads"]:
        upload_query = (
            select(Upload)
            .where(
                Upload.user_id == current_user.id,
                Upload.original_filename.ilike(search_term)
            )
            .limit(limit)
        )
        upload_result = await db.execute(upload_query)
        uploads = upload_result.scalars().all()
        
    return {
        "documents": docs,
        "uploads": uploads
    }
