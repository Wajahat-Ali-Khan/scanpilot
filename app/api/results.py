from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
# from uuid import UUID
from app.db import get_db
from app.models import User, Upload, AuditResult
from app.schemas import ProcessRequest, AuditResultResponse
from app.auth import get_current_user
from app.services.huggingface import hf_service
from app.services.processing import read_file_content

router = APIRouter(prefix="/api/results", tags=["Results"])

@router.post("/process", response_model=AuditResultResponse, status_code=status.HTTP_201_CREATED)
async def process_document(
    request: ProcessRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    text_to_process = request.text
    
    # If upload_id provided, read from file
    if request.upload_id:
        result = await db.execute(
            select(Upload).where(
                Upload.id == request.upload_id,
                Upload.user_id == current_user.id
            )
        )
        upload = result.scalar_one_or_none()
        if not upload:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
        
        text_to_process = await read_file_content(upload.file_path)
    
    if not text_to_process:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No text provided")
    
    # Process with LLM
    analysis_result = await hf_service.analyze_text(text_to_process)
    
    # Save result
    audit_result = AuditResult(
        user_id=current_user.id,
        upload_id=request.upload_id,
        input_text=text_to_process[:500],  # Store first 500 chars
        result_json=analysis_result,
        status=analysis_result.get("status", "completed")
    )
    
    db.add(audit_result)
    await db.commit()
    await db.refresh(audit_result)
    
    return audit_result

@router.get("/", response_model=List[AuditResultResponse])
async def get_results(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(AuditResult)
        .where(AuditResult.user_id == current_user.id)
        .order_by(AuditResult.created_at.desc())
    )
    results = result.scalars().all()
    return results

@router.get("/{result_id}", response_model=AuditResultResponse)
async def get_result(
    result_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(AuditResult).where(
            AuditResult.id == result_id,
            AuditResult.user_id == current_user.id
        )
    )
    audit_result = result.scalar_one_or_none()
    
    if not audit_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")
    
    return audit_result