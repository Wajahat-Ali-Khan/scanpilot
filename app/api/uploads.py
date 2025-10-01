from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User, Upload
from app.schemas import UploadResponse
from app.auth import get_current_user
from app.services.processing import save_upload_file

router = APIRouter(prefix="/api/uploads", tags=["Uploads"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".doc"}

@router.post("/", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Validate file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Supported: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    try:
        # Save file
        file_path, file_size = await save_upload_file(file, str(current_user.id))
        
        # Create database record
        upload = Upload(
            user_id=current_user.id,
            file_path=file_path,
            original_filename=file.filename,
            file_size=file_size,
            mime_type=file.content_type
        )
        
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        
        return upload
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))