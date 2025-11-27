"""
Comment Service - Business logic for document comments.

This service handles all comment-related operations including
creation, retrieval, and resolution.
"""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app import models, schemas


class CommentService:
    """Service class for comment operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_comment(
        self,
        document_id: int,
        user_id: int,
        content: str,
        position_start: Optional[int] = None,
        position_end: Optional[int] = None
    ) -> models.Comment:
        """
        Create a new comment on a document.
        
        Args:
            document_id: Document ID
            user_id: User ID creating the comment
            content: Comment content
            position_start: Start position in document (optional)
            position_end: End position in document (optional)
            
        Returns:
            Created comment
        """
        new_comment = models.Comment(
            document_id=document_id,
            user_id=user_id,
            content=content,
            position_start=position_start,
            position_end=position_end
        )
        self.db.add(new_comment)
        await self.db.commit()
        await self.db.refresh(new_comment)
        return new_comment
    
    async def get_comments(self, document_id: int) -> List[models.Comment]:
        """
        Get all comments for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of comments
        """
        result = await self.db.execute(
            select(models.Comment)
            .where(models.Comment.document_id == document_id)
            .order_by(models.Comment.created_at.desc())
        )
        return result.scalars().all()
    
    async def resolve_comment(self, comment_id: int, user_id: int) -> models.Comment:
        """
        Mark a comment as resolved.
        
        Args:
            comment_id: Comment ID
            user_id: User ID resolving the comment
            
        Returns:
            Updated comment
            
        Raises:
            HTTPException: If comment not found
        """
        result = await self.db.execute(
            select(models.Comment).where(models.Comment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        comment.resolved = True
        await self.db.commit()
        await self.db.refresh(comment)
        return comment
