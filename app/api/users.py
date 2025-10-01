from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import User
from app.schemas import UserResponse, UserUpdate
from app.auth import get_current_user, get_password_hash

router = APIRouter(prefix="/api/users", tags=["Users"])

@router.get("/profile", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user

@router.put("/profile", response_model=UserResponse)
async def update_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name
    
    if user_update.email is not None:
        current_user.email = user_update.email
    
    if user_update.password is not None:
        current_user.hashed_password = get_password_hash(user_update.password)
    
    await db.commit()
    await db.refresh(current_user)
    
    return current_user