from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db import get_db
from app.models import User, Upload, AuditResult
from app.schemas import UploadWithStatusResponse, ProcessFileRequest, FileProcessingResponse
from app.auth import get_current_user
from app.services.processing import save_upload_file
from app.services.file_processor import FileProcessor
from app.services.huggingface import hf_service
from typing import List
from uuid import UUID
import os

router = APIRouter(prefix="/api/uploads", tags=["Uploads"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".doc"}

@router.post("/", response_model=UploadWithStatusResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload file without processing - status will be 'pending'"""
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Supported: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    try:
        file_path, file_size = await save_upload_file(file, str(current_user.id))
        
        upload = Upload(
            user_id=current_user.id,
            file_path=file_path,
            original_filename=file.filename,
            file_size=file_size,
            mime_type=file.content_type,
            status="pending"  # Set as pending, not processing
        )
        
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        
        return upload
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/", response_model=List[UploadWithStatusResponse])
async def get_all_uploads(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all uploaded files for current user"""
    result = await db.execute(
        select(Upload)
        .where(Upload.user_id == current_user.id)
        .order_by(Upload.created_at.desc())
    )
    uploads = result.scalars().all()
    return uploads


@router.post("/process", response_model=FileProcessingResponse)
async def process_file(
    request: ProcessFileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Process an uploaded file - actual processing, no mock data"""
    
    # Get upload record
    result = await db.execute(
        select(Upload).where(
            Upload.id == request.upload_id,
            Upload.user_id == current_user.id
        )
    )
    upload = result.scalar_one_or_none()
    
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    
    if upload.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is already being processed"
        )
    
    if upload.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File has already been processed"
        )
    
    # Update status to processing
    await db.execute(
        update(Upload)
        .where(Upload.id == request.upload_id)
        .values(status="processing", error_message=None)
    )
    await db.commit()
    
    # CONSUME CREDITS BEFORE PROCESSING
    try:
        from app.api.credits import get_credit_cost, consume_credits
        
        # Get the credit cost for file processing
        credit_cost = await get_credit_cost("file_processing", db)
        
        # Consume credits
        await consume_credits(
            user_id=current_user.id,
            amount=credit_cost,
            operation_type="file_processing",
            description=f"File processing: {upload.original_filename}",
            metadata={
                "operation_type": "file_processing",
                "upload_id": upload.id,
                "filename": upload.original_filename,
                "file_size": upload.file_size
            },
            db=db
        )
    except HTTPException as e:
        # Revert status if credit deduction fails
        await db.execute(
            update(Upload)
            .where(Upload.id == request.upload_id)
            .values(status="pending", error_message=str(e.detail))
        )
        await db.commit()
        raise e
    
    try:
        # Step 1: Extract text from file (REAL PROCESSING)
        file_processor = FileProcessor()
        text_content = await file_processor.extract_text_from_file(
            upload.file_path,
            upload.mime_type or "text/plain"
        )
        
        if not text_content or len(text_content.strip()) < 10:
            raise ValueError("File appears to be empty or contains insufficient text")
        
        # Step 2: Perform document analysis (REAL ANALYSIS)
        document_analysis = file_processor.analyze_document(text_content)
        
        # Step 3: Get AI insights from Hugging Face (REAL AI)
        ai_analysis = await hf_service.analyze_text(
            text_content[:1000],  # First 1000 chars for AI
            # request.model_name
        )
        
        # Combine results
        combined_result = {
            **ai_analysis,
            "document_metrics": document_analysis,
            "text_preview": text_content[:500],
            "total_characters": len(text_content)
        }
        
        # Step 4: Save result to database
        audit_result = AuditResult(
            user_id=current_user.id,
            upload_id=upload.id,
            input_text=text_content[:500],
            result_json=combined_result,
            status="completed"
        )
        db.add(audit_result)
        
        # Step 5: Update upload status
        await db.execute(
            update(Upload)
            .where(Upload.id == request.upload_id)
            .values(status="completed", error_message=None)
        )
        
        await db.commit()
        await db.refresh(audit_result)
        
        return FileProcessingResponse(
            upload_id=upload.id,
            status="completed",
            message="File processed successfully",
            result_id=audit_result.id
        )
        
    except Exception as e:
        # Mark as failed with error message
        await db.execute(
            update(Upload)
            .where(Upload.id == request.upload_id)
            .values(status="failed", error_message=str(e))
        )
        await db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}"
        )


@router.get("/{upload_id}", response_model=UploadWithStatusResponse)
async def get_upload_by_id(
    upload_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific upload details"""
    result = await db.execute(
        select(Upload).where(
            Upload.id == upload_id,
            Upload.user_id == current_user.id
        )
    )
    upload = result.scalar_one_or_none()
    
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    
    return upload


@router.delete("/{upload_id}")
async def delete_upload(
    upload_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an uploaded file"""
    result = await db.execute(
        select(Upload).where(
            Upload.id == upload_id,
            Upload.user_id == current_user.id
        )
    )
    upload = result.scalar_one_or_none()
    
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    
    # Delete file from filesystem
    try:
        if upload.file_path and os.path.exists(upload.file_path):
            os.remove(upload.file_path)
    except Exception as e:
        print(f"Warning: Could not delete file: {e}")
    
    # Delete from database
    await db.delete(upload)
    await db.commit()
    
    return {"message": "File deleted successfully"}