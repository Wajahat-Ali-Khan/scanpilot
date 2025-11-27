"""
Document Service - Business logic for document operations.

This service encapsulates all document-related business logic,
separating it from the API layer for better maintainability and testability.
"""

from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app import models, schemas
from app.api.credits import get_credit_cost, consume_credits


class DocumentService:
    """Service class for document operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_document(
        self,
        title: str,
        content: str,
        owner_id: int
    ) -> models.Document:
        """
        Create a new document.
        
        Args:
            title: Document title
            content: Document content
            owner_id: ID of the document owner
            
        Returns:
            Created document
        """
        new_doc = models.Document(
            title=title,
            content=content,
            owner_id=owner_id
        )
        self.db.add(new_doc)
        await self.db.commit()
        await self.db.refresh(new_doc)
        return new_doc
    
    async def get_document(self, doc_id: int) -> models.Document:
        """
        Get a document by ID.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Document
            
        Raises:
            HTTPException: If document not found
        """
        result = await self.db.execute(
            select(models.Document).where(models.Document.id == doc_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        return doc
    
    async def get_documents_paginated(
        self,
        owner_id: int,
        page: int = 1,
        size: int = 10
    ) -> Dict[str, Any]:
        """
        Get paginated documents for a user.
        
        Args:
            owner_id: Owner user ID
            page: Page number (1-indexed)
            size: Page size
            
        Returns:
            Dictionary with items, total, page, size, and pages
        """
        offset = (page - 1) * size
        
        # Get total count
        count_query = select(func.count()).select_from(models.Document).where(
            models.Document.owner_id == owner_id
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()
        
        # Get items
        query = (
            select(models.Document)
            .where(models.Document.owner_id == owner_id)
            .order_by(models.Document.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self.db.execute(query)
        items = result.scalars().all()
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size
        }
    
    async def update_document(
        self,
        doc_id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        created_by: Optional[int] = None
    ) -> models.Document:
        """
        Update a document.
        
        Args:
            doc_id: Document ID
            title: New title (optional)
            content: New content (optional)
            created_by: User ID creating the version (for versioning)
            
        Returns:
            Updated document
            
        Raises:
            HTTPException: If document not found
        """
        doc = await self.get_document(doc_id)
        
        if title is not None:
            doc.title = title
        
        if content is not None:
            # Create a version before updating
            version = models.DocumentVersion(
                document_id=doc.id,
                content=doc.content if doc.content else "",
                created_by=created_by
            )
            self.db.add(version)
            doc.content = content
        
        await self.db.commit()
        await self.db.refresh(doc)
        return doc
    
    async def update_title(self, doc_id: int, title: str) -> models.Document:
        """
        Update document title only.
        
        Args:
            doc_id: Document ID
            title: New title
            
        Returns:
            Updated document
        """
        doc = await self.get_document(doc_id)
        doc.title = title
        await self.db.commit()
        await self.db.refresh(doc)
        return doc
    
    async def delete_document(self, doc_id: int, owner_id: int) -> None:
        """
        Delete a document.
        
        Args:
            doc_id: Document ID
            owner_id: Owner user ID (for authorization check)
            
        Raises:
            HTTPException: If document not found or user not authorized
        """
        doc = await self.get_document(doc_id)
        
        # Check ownership
        if doc.owner_id != owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this document"
            )
        
        await self.db.delete(doc)
        await self.db.commit()
    
    async def create_from_upload(
        self,
        upload_id: int,
        owner_id: int
    ) -> models.Document:
        """
        Create a document from an upload.
        
        Args:
            upload_id: Upload ID
            owner_id: Owner user ID
            
        Returns:
            Created document
            
        Raises:
            HTTPException: If upload not found
        """
        # Get the upload
        result = await self.db.execute(
            select(models.Upload).where(models.Upload.id == upload_id)
        )
        upload = result.scalar_one_or_none()
        if not upload:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upload not found"
            )
        
        # Check if document already exists
        result = await self.db.execute(
            select(models.Document).where(
                models.Document.owner_id == owner_id,
                models.Document.title == upload.original_filename
            )
        )
        existing_doc = result.scalars().first()
        if existing_doc:
            return existing_doc
        
        # Get content from AuditResult
        result = await self.db.execute(
            select(models.AuditResult).where(
                models.AuditResult.upload_id == upload_id
            )
        )
        audit = result.scalars().first()
        content = audit.input_text if audit else ""
        
        # Consume credits
        credit_cost = await get_credit_cost("document_creation", self.db)
        await consume_credits(
            user_id=owner_id,
            amount=credit_cost,
            operation_type="document_creation",
            description=f"Document created from upload: {upload.original_filename}",
            metadata={
                "operation_type": "document_creation",
                "upload_id": upload_id,
                "filename": upload.original_filename
            },
            db=self.db
        )
        
        # Create document
        return await self.create_document(
            title=upload.original_filename,
            content=content,
            owner_id=owner_id
        )
    
    async def get_versions(self, doc_id: int) -> List[Dict[str, Any]]:
        """
        Get version history for a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            List of version dictionaries with user info
        """
        result = await self.db.execute(
            select(models.DocumentVersion, models.User)
            .join(
                models.User,
                models.DocumentVersion.created_by == models.User.id,
                isouter=True
            )
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
    
    async def get_ai_suggestions(
        self,
        doc_id: int,
        context: str,
        selection: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Get AI-powered suggestions for document text.
        
        Args:
            doc_id: Document ID
            context: Context text
            selection: Selected text
            user_id: User ID (for credit consumption)
            
        Returns:
            AI suggestions
            
        Raises:
            HTTPException: If document not found
        """
        from app.services.ai import generate_suggestion
        
        # Verify document exists
        doc = await self.get_document(doc_id)
        
        # Consume credits
        credit_cost = await get_credit_cost("ai_suggestion", self.db)
        await consume_credits(
            user_id=user_id,
            amount=credit_cost,
            operation_type="ai_suggestion",
            description=f"AI suggestion for document: {doc.title}",
            metadata={
                "operation_type": "ai_suggestion",
                "document_id": doc_id,
                "document_title": doc.title
            },
            db=self.db
        )
        
        # Generate suggestions
        suggestions = await generate_suggestion(context, selection)
        return suggestions
