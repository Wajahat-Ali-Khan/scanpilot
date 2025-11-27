from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any
from app.db import get_db
from app import models, schemas
from app.auth import get_current_user
from app.middleware.subscription import check_document_limit, check_collaborator_limit
from app.services.document_service import DocumentService
from app.services.comment_service import CommentService

router = APIRouter(
    prefix="/api/documents",
    tags=["documents"]
)


def get_document_service(db: AsyncSession = Depends(get_db)) -> DocumentService:
    """Dependency to get DocumentService instance."""
    return DocumentService(db)


def get_comment_service(db: AsyncSession = Depends(get_db)) -> CommentService:
    """Dependency to get CommentService instance."""
    return CommentService(db)


@router.post("/", response_model=schemas.DocumentResponse)
async def create_document(
    doc: schemas.DocumentCreate,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    doc_service: DocumentService = Depends(get_document_service)
) -> models.Document:
    """Create a new document."""
    # Check if user has reached document limit
    await check_document_limit(current_user, db)
    
    return await doc_service.create_document(
        title=doc.title,
        content=doc.content,
        owner_id=current_user.id
    )


@router.get("/", response_model=schemas.PaginatedResponse[schemas.DocumentResponse])
async def get_documents(
    page: int = 1,
    size: int = 10,
    current_user: models.User = Depends(get_current_user),
    doc_service: DocumentService = Depends(get_document_service)
) -> Dict[str, Any]:
    """Get paginated list of user's documents."""
    return await doc_service.get_documents_paginated(
        owner_id=current_user.id,
        page=page,
        size=size
    )


@router.get("/{doc_id}", response_model=schemas.DocumentResponse)
async def get_document(
    doc_id: int,
    doc_service: DocumentService = Depends(get_document_service)
) -> models.Document:
    """Get a specific document by ID."""
    return await doc_service.get_document(doc_id)


@router.put("/{doc_id}", response_model=schemas.DocumentResponse)
async def update_document(
    doc_id: int,
    doc_update: schemas.DocumentUpdate,
    current_user: models.User = Depends(get_current_user),
    doc_service: DocumentService = Depends(get_document_service)
) -> models.Document:
    """Update a document's title and/or content."""
    return await doc_service.update_document(
        doc_id=doc_id,
        title=doc_update.title,
        content=doc_update.content,
        created_by=current_user.id
    )


@router.patch("/{doc_id}/title", response_model=schemas.DocumentResponse)
async def update_document_title(
    doc_id: int,
    title_update: schemas.DocumentTitleUpdate,
    doc_service: DocumentService = Depends(get_document_service)
) -> models.Document:
    """Update only the document title."""
    return await doc_service.update_title(doc_id, title_update.title)


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: int,
    current_user: models.User = Depends(get_current_user),
    doc_service: DocumentService = Depends(get_document_service)
) -> Dict[str, str]:
    """Delete a document."""
    await doc_service.delete_document(doc_id, current_user.id)
    return {"message": "Document deleted successfully"}


@router.post("/from_upload/{upload_id}", response_model=schemas.DocumentResponse)
async def create_document_from_upload(
    upload_id: int,
    current_user: models.User = Depends(get_current_user),
    doc_service: DocumentService = Depends(get_document_service)
) -> models.Document:
    """Create a document from an uploaded file."""
    return await doc_service.create_from_upload(
        upload_id=upload_id,
        owner_id=current_user.id
    )


@router.get("/{doc_id}/versions", response_model=List[schemas.DocumentVersionResponse])
async def get_versions(
    doc_id: int,
    doc_service: DocumentService = Depends(get_document_service)
) -> List[Dict[str, Any]]:
    """Get version history for a document."""
    return await doc_service.get_versions(doc_id)


@router.post("/{doc_id}/comments", response_model=schemas.CommentResponse)
async def add_comment(
    doc_id: int,
    comment: schemas.CommentCreate,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    comment_service: CommentService = Depends(get_comment_service)
) -> models.Comment:
    """Add a comment to a document."""
    # Check collaborator limit
    await check_collaborator_limit(doc_id, current_user, db)
    
    return await comment_service.create_comment(
        document_id=doc_id,
        user_id=current_user.id,
        content=comment.content,
        position_start=comment.position_start,
        position_end=comment.position_end
    )


@router.get("/{doc_id}/comments", response_model=List[schemas.CommentResponse])
async def get_comments(
    doc_id: int,
    comment_service: CommentService = Depends(get_comment_service)
) -> List[models.Comment]:
    """Get all comments for a document."""
    return await comment_service.get_comments(doc_id)


@router.post("/{doc_id}/ai-suggest")
async def get_ai_suggestions(
    doc_id: int,
    request: dict,
    current_user: models.User = Depends(get_current_user),
    doc_service: DocumentService = Depends(get_document_service)
) -> Dict[str, Any]:
    """Get AI-powered suggestions for document text."""
    context = request.get("context", "")
    selection = request.get("selection", "")
    
    return await doc_service.get_ai_suggestions(
        doc_id=doc_id,
        context=context,
        selection=selection,
        user_id=current_user.id
    )
