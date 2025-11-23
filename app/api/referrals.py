from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from datetime import datetime
import secrets
import string

from ..db import get_db
from .. import models, schemas
from app.auth import get_current_user

router = APIRouter(
    prefix="/api/referrals",
    tags=["Referrals"],
    dependencies=[Depends(get_current_user)]
)

def generate_referral_code(length=8):
    """Generate a unique referral code"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

@router.get("/me", response_model=schemas.ReferralStatsResponse)
async def get_my_referrals(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get user's referral statistics"""
    # Get or create referral code
    result = await db.execute(
        select(models.Referral).where(
            and_(
                models.Referral.referrer_id == current_user.id,
                models.Referral.referee_id == None  # The user's main referral code
            )
        ).limit(1)
    )
    referral = result.scalar_one_or_none()
    
    if not referral:
        # Create new referral code
        code = generate_referral_code()
        referral = models.Referral(
            referrer_id=current_user.id,
            referral_code=code,
            status="pending"
        )
        db.add(referral)
        await db.commit()
        await db.refresh(referral)
    
    # Get all referrals made by this user
    all_referrals_result = await db.execute(
        select(models.Referral).where(models.Referral.referrer_id == current_user.id)
    )
    all_referrals = all_referrals_result.scalars().all()
    
    # Calculate stats
    total_referrals = len([r for r in all_referrals if r.referee_id is not None])
    successful_referrals = len([r for r in all_referrals if r.status == "rewarded"])
    pending_referrals = len([r for r in all_referrals if r.status in ["pending", "completed"]])
    total_credits_earned = sum(r.bonus_credits for r in all_referrals if r.status == "rewarded")
    
    return schemas.ReferralStatsResponse(
        referral_code=referral.referral_code,
        total_referrals=total_referrals,
        successful_referrals=successful_referrals,
        pending_referrals=pending_referrals,
        total_credits_earned=total_credits_earned
    )

@router.post("/generate-code", response_model=schemas.ReferralResponse)
async def generate_code(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Generate a new referral code for the user"""
    # Check if user already has a code
    result = await db.execute(
        select(models.Referral).where(
            and_(
                models.Referral.referrer_id == current_user.id,
                models.Referral.referee_id == None
            )
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        return existing
    
    # Create new code
    code = generate_referral_code()
    referral = models.Referral(
        referrer_id=current_user.id,
        referral_code=code,
        status="pending"
    )
    db.add(referral)
    await db.commit()
    await db.refresh(referral)
    
    return referral

@router.post("/apply/{code}", response_model=dict)
async def apply_referral_code(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Apply a referral code to receive bonus credits"""
    # Get the referral code
    result = await db.execute(
        select(models.Referral).where(models.Referral.referral_code == code.upper())
    )
    referral = result.scalar_one_or_none()
    
    if not referral:
        raise HTTPException(status_code=404, detail="Invalid referral code")
    
    # Check if user is referring themselves
    if referral.referrer_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot use your own referral code")
    
    # Check if user has already used a referral code
    existing_result = await db.execute(
        select(models.Referral).where(models.Referral.referee_id == current_user.id)
    )
    existing_referral = existing_result.scalar_one_or_none()
    
    if existing_referral:
        raise HTTPException(status_code=400, detail="You have already used a referral code")
    
    # Create a new referral record for this specific referral
    new_referral = models.Referral(
        referrer_id=referral.referrer_id,
        referee_id=current_user.id,
        referral_code=code.upper(),
        status="completed",
        bonus_credits=50,  # Bonus for referee
        completed_at=datetime.utcnow()
    )
    db.add(new_referral)
    
    # Grant bonus credits to referee (the current user)
    referee_sub_result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == current_user.id)
    )
    referee_subscription = referee_sub_result.scalar_one_or_none()
    
    if referee_subscription:
        referee_subscription.credits_remaining += 50
        
        # Create credit transaction
        referee_transaction = models.CreditTransaction(
            user_id=current_user.id,
            subscription_id=referee_subscription.id,
            amount=50,
            transaction_type="bonus",
            description=f"Referral bonus from code {code}",
            metadata_json={"referral_code": code, "type": "referee_bonus"}
        )
        db.add(referee_transaction)
    
    # Grant bonus credits to referrer
    referrer_sub_result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == referral.referrer_id)
    )
    referrer_subscription = referrer_sub_result.scalar_one_or_none()
    
    if referrer_subscription:
        # Referrer gets 1 month free Pro (or equivalent credits)
        # For simplicity, giving 500 bonus credits
        referrer_subscription.credits_remaining += 500
        
        # Update referral status
        referral.status = "rewarded"
        new_referral.status = "rewarded"
        
        # Create credit transaction for referrer
        referrer_transaction = models.CreditTransaction(
            user_id=referral.referrer_id,
            subscription_id=referrer_subscription.id,
            amount=500,
            transaction_type="bonus",
            description=f"Referral reward - {current_user.email} signed up",
            metadata_json={"referee_id": current_user.id, "type": "referrer_bonus"}
        )
        db.add(referrer_transaction)
    
    await db.commit()
    
    return {
        "message": "Referral code applied successfully!",
        "credits_awarded": 50,
        "referrer_bonus": 500
    }
