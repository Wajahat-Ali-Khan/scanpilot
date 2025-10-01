from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime
# from uuid import UUID

# User Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)
    email: Optional[EmailStr] = None

# Token Schemas
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None

# Upload Schemas
class UploadResponse(BaseModel):
    id: int
    original_filename: str
    file_size: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# Audit Result Schemas
class ProcessRequest(BaseModel):
    text: Optional[str] = None
    upload_id: Optional[int] = None
    model_name: str = "google/flan-t5-base"

class AuditResultResponse(BaseModel):
    id: int
    input_text: Optional[str]
    result_json: Dict[str, Any]
    status: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)