from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List
from datetime import datetime, timedelta

from ..db import get_db
from .. import models, schemas
from app.auth import get_current_user

router = APIRouter(
    prefix="/api/subscriptions",
    tags=["Subscriptions"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/plans", response_model=List[schemas.PlanResponse])
async def get_plans(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all available subscription plans"""
    result = await db.execute(
        select(models.Plan).where(models.Plan.is_active == True).order_by(models.Plan.id)
    )
    plans = result.scalars().all()
    return plans

@router.get("/me", response_model=schemas.SubscriptionResponse)
async def get_my_subscription(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get current user's subscription details"""
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == current_user.id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        # Auto-create free subscription for existing users
        plan_result = await db.execute(
            select(models.Plan).where(models.Plan.name == "free")
        )
        free_plan = plan_result.scalar_one_or_none()
        
        if not free_plan:
            raise HTTPException(status_code=500, detail="Free plan not initialized")
            
        subscription = models.Subscription(
            user_id=current_user.id,
            plan_id=free_plan.id,
            status="active",
            credits_remaining=free_plan.credits_per_month
        )
        db.add(subscription)
        await db.commit()
        await db.refresh(subscription)
        subscription.plan = free_plan
        return subscription

    # Fetch the plan details
    plan_result = await db.execute(
        select(models.Plan).where(models.Plan.id == subscription.plan_id)
    )
    subscription.plan = plan_result.scalar_one()
    
    return subscription

@router.post("/upgrade", response_model=dict)
async def upgrade_subscription(
    upgrade_request: schemas.SubscriptionUpgradeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Upgrade to a paid plan
    Returns Stripe checkout URL for payment
    """
    # Get the requested plan
    result = await db.execute(
        select(models.Plan).where(models.Plan.name == upgrade_request.plan_name)
    )
    new_plan = result.scalar_one_or_none()
    
    if not new_plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    if new_plan.name == "free":
        raise HTTPException(status_code=400, detail="Cannot upgrade to free plan")
    
    # Get current subscription
    sub_result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == current_user.id)
    )
    subscription = sub_result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found")
    
    # Check if already on this plan
    if subscription.plan_id == new_plan.id:
        raise HTTPException(status_code=400, detail="Already subscribed to this plan")
    
    # Create or get Stripe customer
    from ..services import stripe_service
    
    if not subscription.stripe_customer_id:
        # Create Stripe customer
        customer = await stripe_service.create_customer(
            user_email=current_user.email,
            user_name=current_user.full_name,
            user_id=current_user.id
        )
        subscription.stripe_customer_id = customer.id
        await db.commit()
    
    # Determine pricing based on billing cycle
    price_monthly = float(new_plan.price_monthly)
    price_yearly = float(new_plan.price_yearly)
    
    # Create checkout session
    try:
        checkout_data = await stripe_service.create_checkout_session(
            customer_id=subscription.stripe_customer_id,
            plan_name=new_plan.name,
            price_monthly=price_monthly,
            price_yearly=price_yearly,
            billing_cycle=upgrade_request.billing_cycle,
            user_id=current_user.id
        )
        
        return {
            "message": "Checkout session created",
            "plan": new_plan.display_name,
            "billing_cycle": upgrade_request.billing_cycle,
            "checkout_url": checkout_data["checkout_url"],
            "session_id": checkout_data["session_id"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create checkout session: {str(e)}")

@router.post("/downgrade", response_model=dict)
async def downgrade_subscription(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Downgrade to free plan
    Takes effect at the end of current billing period
    """
    # Get current subscription
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == current_user.id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found")
    
    # Get free plan
    free_plan_result = await db.execute(
        select(models.Plan).where(models.Plan.name == "free")
    )
    free_plan = free_plan_result.scalar_one()
    
    # Check if already on free plan
    if subscription.plan_id == free_plan.id:
        raise HTTPException(status_code=400, detail="Already on free plan")
    
    # Schedule downgrade for end of period
    subscription.status = "cancelled"
    subscription.cancelled_at = datetime.utcnow()
    # Will downgrade when current_period_end is reached
    
    await db.commit()
    await db.refresh(subscription)
    
    return {
        "message": "Downgrade scheduled",
        "effective_date": subscription.current_period_end,
        "new_plan": "free"
    }

@router.post("/cancel", response_model=dict)
async def cancel_subscription(
    cancel_request: schemas.SubscriptionCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Cancel subscription (downgrades to free)"""
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == current_user.id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found")
    
    # Get free plan
    free_plan_result = await db.execute(
        select(models.Plan).where(models.Plan.name == "free")
    )
    free_plan = free_plan_result.scalar_one()
    
    if subscription.plan_id == free_plan.id:
        raise HTTPException(status_code=400, detail="Already on free plan")
    
    if cancel_request.immediate:
        # Immediately downgrade to free
        subscription.plan_id = free_plan.id
        subscription.status = "active"
        subscription.billing_cycle = None
        subscription.stripe_subscription_id = None
        subscription.cancelled_at = datetime.utcnow()
        subscription.credits_remaining = free_plan.credits_per_month
        
        await db.commit()
        
        return {
            "message": "Subscription cancelled immediately",
            "new_plan": "free",
            "effective_date": datetime.utcnow()
        }
    else:
        # Schedule cancellation for end of period
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.utcnow()
        
        await db.commit()
        
        return {
            "message": "Subscription cancellation scheduled",
            "effective_date": subscription.current_period_end,
            "access_until": subscription.current_period_end
        }

@router.get("/credits", response_model=schemas.CreditBalance)
async def get_credit_balance(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get current credit balance"""
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == current_user.id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found")
    
    # Get plan details
    plan_result = await db.execute(
        select(models.Plan).where(models.Plan.id == subscription.plan_id)
    )
    plan = plan_result.scalar_one()
    
    return schemas.CreditBalance(
        credits_remaining=subscription.credits_remaining,
        credits_rollover=subscription.credits_rollover,
        total_credits=subscription.credits_remaining + subscription.credits_rollover,
        plan_credits_per_month=plan.credits_per_month,
        next_renewal_date=subscription.current_period_end
    )
