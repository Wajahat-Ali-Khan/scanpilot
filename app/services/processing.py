import os
import aiofiles
from pathlib import Path
from typing import Optional
from fastapi import UploadFile
from app.config import settings

async def save_upload_file(file: UploadFile, user_id: str) -> tuple[str, int]:
    """Save uploaded file and return path and size"""
    upload_dir = Path(settings.UPLOAD_DIR) / str(user_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / file.filename
    
    size = 0
    async with aiofiles.open(file_path, 'wb') as f:
        while chunk := await file.read(8192):
            size += len(chunk)
            if size > settings.MAX_FILE_SIZE:
                # Clean up and raise error
                await file.close()
                os.remove(file_path)
                raise ValueError(f"File size exceeds {settings.MAX_FILE_SIZE} bytes")
            await f.write(chunk)
    
    return str(file_path), size

async def read_file_content(file_path: str) -> str:
    """Read content from uploaded file"""
    async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = await f.read()
    return content