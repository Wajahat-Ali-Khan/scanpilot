from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.db import get_db
from app import models, schemas
from app.auth import get_current_user
from app.middleware.subscription import check_collaborator_limit

router = APIRouter(
    prefix="/api/documents/{doc_id}/collaborators",
    tags=["collaborators"]
)

@router.post("/", response_model=schemas.CollaboratorResponse)
async def invite_collaborator(
    doc_id: int,
    invite: schemas.CollaboratorInvite,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Invite a collaborator to a document"""
    # Get document and verify ownership
    result = await db.execute(select(models.Document).where(models.Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if doc.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only document owner can invite collaborators")
    
    # Check collaborator limit
    await check_collaborator_limit(doc_id, current_user, db)
    
    # Find user by email
    user_result = await db.execute(select(models.User).where(models.User.email == invite.email))
    invited_user = user_result.scalar_one_or_none()
    
    if not invited_user:
        raise HTTPException(status_code=404, detail=f"User with email {invite.email} not found")
    
    if invited_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot invite yourself")
    
    # Check if already a collaborator
    existing = await db.execute(
        select(models.DocumentCollaborator).where(
            models.DocumentCollaborator.document_id == doc_id,
            models.DocumentCollaborator.user_id == invited_user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a collaborator")
    
    # Create collaborator
    collaborator = models.DocumentCollaborator(
        document_id=doc_id,
        user_id=invited_user.id,
        role=invite.role,
        invited_by=current_user.id
    )
    db.add(collaborator)
    await db.commit()
    await db.refresh(collaborator)
    
    # Build response with user info
    return schemas.CollaboratorResponse(
        id=collaborator.id,
        document_id=collaborator.document_id,
        user_id=collaborator.user_id,
        role=collaborator.role,
        invited_by=collaborator.invited_by,
        created_at=collaborator.created_at,
        user_email=invited_user.email,
        user_name=invited_user.full_name
    )

@router.get("/", response_model=List[schemas.CollaboratorResponse])
async def get_collaborators(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all collaborators for a document"""
    # Verify document exists and user has access
    doc_result = await db.execute(select(models.Document).where(models.Document.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get collaborators with user info
    result = await db.execute(
        select(models.DocumentCollaborator, models.User)
        .join(models.User, models.DocumentCollaborator.user_id == models.User.id)
        .where(models.DocumentCollaborator.document_id == doc_id)
    )
    
    collaborators_with_users = result.all()
    
    # Build response
    response = []
    for collab, user in collaborators_with_users:
        response.append(schemas.CollaboratorResponse(
            id=collab.id,
            document_id=collab.document_id,
            user_id=collab.user_id,
            role=collab.role,
            invited_by=collab.invited_by,
            created_at=collab.created_at,
            user_email=user.email,
            user_name=user.full_name
        ))
    
    return response

@router.delete("/{user_id}")
async def remove_collaborator(
    doc_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Remove a collaborator from a document"""
    # Get document and verify ownership
    doc_result = await db.execute(select(models.Document).where(models.Document.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if doc.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only document owner can remove collaborators")
    
    # Find and delete collaborator
    collab_result = await db.execute(
        select(models.DocumentCollaborator).where(
            models.DocumentCollaborator.document_id == doc_id,
            models.DocumentCollaborator.user_id == user_id
        )
    )
    collaborator = collab_result.scalar_one_or_none()
    
    if not collaborator:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    
    await db.delete(collaborator)
    await db.commit()
    
    return {"message": "Collaborator removed successfully"}

@router.patch("/{user_id}", response_model=schemas.CollaboratorResponse)
async def update_collaborator_role(
    doc_id: int,
    user_id: int,
    update: schemas.CollaboratorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Update a collaborator's role"""
    # Get document and verify ownership
    doc_result = await db.execute(select(models.Document).where(models.Document.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if doc.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only document owner can update collaborator roles")
    
    # Find collaborator
    collab_result = await db.execute(
        select(models.DocumentCollaborator, models.User)
        .join(models.User, models.DocumentCollaborator.user_id == models.User.id)
        .where(
            models.DocumentCollaborator.document_id == doc_id,
            models.DocumentCollaborator.user_id == user_id
        )
    )
    result_tuple = collab_result.first()
    
    if not result_tuple:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    
    collaborator, user = result_tuple
    
    # Update role
    collaborator.role = update.role
    await db.commit()
    await db.refresh(collaborator)
    
    return schemas.CollaboratorResponse(
        id=collaborator.id,
        document_id=collaborator.document_id,
        user_id=collaborator.user_id,
        role=collaborator.role,
        invited_by=collaborator.invited_by,
        created_at=collaborator.created_at,
        user_email=user.email,
        user_name=user.full_name
    )
