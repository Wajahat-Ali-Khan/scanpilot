from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.db import get_db
from app import models, schemas
from app.auth import get_current_user
from app.middleware.subscription import check_document_limit, check_collaborator_limit

router = APIRouter(
    prefix="/api/documents",
    tags=["documents"]
)

@router.post("/", response_model=schemas.DocumentResponse)
async def create_document(
    doc: schemas.DocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Check if user has reached document limit
    await check_document_limit(current_user, db)
    
    new_doc = models.Document(
        title=doc.title,
        content=doc.content,
        owner_id=current_user.id
    )
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)
    return new_doc

@router.get("/", response_model=List[schemas.DocumentResponse])
async def get_documents(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.Document).where(models.Document.owner_id == current_user.id))
    return result.scalars().all()

@router.get("/{doc_id}", response_model=schemas.DocumentResponse)
async def get_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.Document).where(models.Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@router.put("/{doc_id}", response_model=schemas.DocumentResponse)
async def update_document(
    doc_id: int,
    doc_update: schemas.DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.Document).where(models.Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if doc_update.title is not None:
        doc.title = doc_update.title
    if doc_update.content is not None:
        # Create a version before updating
        version = models.DocumentVersion(
            document_id=doc.id,
            content=doc.content if doc.content else "",
            created_by=current_user.id
        )
        db.add(version)
        doc.content = doc_update.content
        
    await db.commit()
    await db.refresh(doc)
    return doc

@router.post("/{doc_id}/comments", response_model=schemas.CommentResponse)
async def add_comment(
    doc_id: int,
    comment: schemas.CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.Document).where(models.Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check collaborator limit
    await check_collaborator_limit(doc_id, current_user, db)
        
    new_comment = models.Comment(
        document_id=doc_id,
        user_id=current_user.id,
        content=comment.content,
        position_start=comment.position_start,
        position_end=comment.position_end
    )
    db.add(new_comment)
    await db.commit()
    await db.refresh(new_comment)
    return new_comment

@router.get("/{doc_id}/comments", response_model=List[schemas.CommentResponse])
async def get_comments(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.Comment).where(models.Comment.document_id == doc_id))
    return result.scalars().all()

@router.get("/{doc_id}/versions", response_model=List[schemas.DocumentVersionResponse])
async def get_versions(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Join with User table to get creator information
    result = await db.execute(
        select(models.DocumentVersion, models.User)
        .join(models.User, models.DocumentVersion.created_by == models.User.id, isouter=True)
        .where(models.DocumentVersion.document_id == doc_id)
        .order_by(models.DocumentVersion.created_at.desc())
    )
    
    versions_with_users = result.all()
    
    # Build response with user info
    response = []
    for version, user in versions_with_users:
        version_dict = {
            "id": version.id,
            "document_id": version.document_id,
            "content": version.content,
            "created_at": version.created_at,
            "created_by": version.created_by,
            "created_by_email": user.email if user else None,
            "created_by_name": user.full_name if user else None
        }
        response.append(version_dict)
    
    return response

@router.patch("/{doc_id}/title", response_model=schemas.DocumentResponse)
async def update_document_title(
    doc_id: int,
    title_update: schemas.DocumentTitleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.Document).where(models.Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc.title = title_update.title
    await db.commit()
    await db.refresh(doc)
    return doc

@router.post("/{doc_id}/ai-suggest")
async def get_ai_suggestions(
    doc_id: int,
    request: dict,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get AI-powered suggestions for document text"""
    from app.services.ai import generate_suggestion
    
    # Verify document exists and user has access
    result = await db.execute(select(models.Document).where(models.Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    context = request.get("context", "")
    selection = request.get("selection", "")
    
    suggestions = await generate_suggestion(context, selection)
    return suggestions


@router.post("/from_upload/{upload_id}", response_model=schemas.DocumentResponse)
async def create_document_from_upload(
    upload_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Get the upload
    result = await db.execute(select(models.Upload).where(models.Upload.id == upload_id))
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # 2. Check if a document with this title already exists for this user
    # This is a heuristic to avoid duplicates. Ideally we'd have a foreign key.
    result = await db.execute(
        select(models.Document).where(
            models.Document.owner_id == current_user.id,
            models.Document.title == upload.original_filename
        )
    )
    existing_doc = result.scalars().first()
    if existing_doc:
        return existing_doc

    # 3. Get the content from AuditResult
    result = await db.execute(select(models.AuditResult).where(models.AuditResult.upload_id == upload_id))
    audit = result.scalars().first()
    content = audit.input_text if audit else ""

    # 4. Create new document
    new_doc = models.Document(
        title=upload.original_filename,
        content=content,
        owner_id=current_user.id
    )
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)
    return new_doc

@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(select(models.Document).where(models.Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check ownership
    if doc.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this document")

    await db.delete(doc)
    await db.commit()
    return None
