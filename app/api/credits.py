from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from typing import List
from datetime import datetime, timedelta

from ..db import get_db
from .. import models, schemas
from app.auth import get_current_user

router = APIRouter(
    prefix="/api/credits",
    tags=["Credits"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/balance", response_model=schemas.CreditBalance)
async def get_balance(
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

@router.get("/transactions", response_model=List[schemas.CreditTransactionResponse])
async def get_transactions(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get credit transaction history"""
    result = await db.execute(
        select(models.CreditTransaction)
        .where(models.CreditTransaction.user_id == current_user.id)
        .order_by(desc(models.CreditTransaction.created_at))
        .limit(limit)
        .offset(offset)
    )
    transactions = result.scalars().all()
    return transactions

@router.post("/purchase", response_model=dict)
async def purchase_credits(
    purchase_request: schemas.CreditPurchaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Purchase additional credit packs
    $5 for 50 credits
    """
    CREDIT_PACK_SIZE = 50
    CREDIT_PACK_PRICE = 5.00
    
    total_credits = purchase_request.amount * CREDIT_PACK_SIZE
    total_price = purchase_request.amount * CREDIT_PACK_PRICE
    total_cents = int(total_price * 100)
    
    # Get user's subscription for Stripe customer  ID
    sub_result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == current_user.id)
    )
    subscription = sub_result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found")
    
    # Create or get Stripe customer
    from ..services import stripe_service
    
    if not subscription.stripe_customer_id:
        customer = await stripe_service.create_customer(
            user_email=current_user.email,
            user_name=current_user.full_name,
            user_id=current_user.id
        )
        subscription.stripe_customer_id = customer.id
        await db.commit()
    
    # Create payment intent
    try:
        payment_data = await stripe_service.create_payment_intent_for_credits(
            customer_id=subscription.stripe_customer_id,
            amount_cents=total_cents,
            credits=total_credits
        )
        
        return {
            "message": "Payment intent created",
            "credits_to_add": total_credits,
            "total_price": total_price,
            "client_secret": payment_data["client_secret"],
            "publishable_key": payment_data["publishable_key"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create payment: {str(e)}")

@router.get("/usage-stats", response_model=schemas.UsageStatsResponse)
async def get_usage_stats(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get monthly usage statistics"""
    # Get subscription
    sub_result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == current_user.id)
    )
    subscription = sub_result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found")
    
    # Get plan
    plan_result = await db.execute(
        select(models.Plan).where(models.Plan.id == subscription.plan_id)
    )
    plan = plan_result.scalar_one()
    
    # Calculate credits used in current period
    period_start = subscription.current_period_start
    period_end = subscription.current_period_end or datetime.utcnow()
    
    # Get usage transactions in current period
    usage_result = await db.execute(
        select(func.sum(models.CreditTransaction.amount))
        .where(
            and_(
                models.CreditTransaction.user_id == current_user.id,
                models.CreditTransaction.transaction_type == 'usage',
                models.CreditTransaction.created_at >= period_start,
                models.CreditTransaction.created_at <= period_end
            )
        )
    )
    credits_used_value = usage_result.scalar()
    credits_used = abs(credits_used_value) if credits_used_value else 0
    
    # Get top operations
    top_ops_result = await db.execute(
        select(
            models.CreditTransaction.metadata_json['operation_type'].astext.label('operation'),
            func.count().label('count'),
            func.sum(func.abs(models.CreditTransaction.amount)).label('total_credits')
        )
        .where(
            and_(
                models.CreditTransaction.user_id == current_user.id,
                models.CreditTransaction.transaction_type == 'usage',
                models.CreditTransaction.created_at >= period_start
            )
        )
        .group_by(models.CreditTransaction.metadata_json['operation_type'].astext)
        .order_by(desc('total_credits'))
        .limit(5)
    )
    top_operations = [
        {
            "operation": row.operation or "unknown",
            "count": row.count,
            "credits_used": row.total_credits or 0
        }
        for row in top_ops_result.all()
    ]
    
    # Calculate usage percentage
    total_allocated = plan.credits_per_month + subscription.credits_rollover
    usage_percentage = (credits_used / total_allocated * 100) if total_allocated > 0 else 0
    
    return schemas.UsageStatsResponse(
        current_period_start=period_start,
        current_period_end=period_end,
        credits_used=credits_used,
        credits_remaining=subscription.credits_remaining,
        total_credits_allocated=total_allocated,
        usage_percentage=round(usage_percentage, 2),
        top_operations=top_operations
    )

async def consume_credits(
    user_id: int,
    amount: int,
    operation_type: str,
    description: str,
    metadata: dict = None,
    db: AsyncSession = None
):
    """
    Internal function to consume credits
    Used by other endpoints that need credit validation
    """
    # Get subscription
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == user_id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found")
    
   # Check if enough credits
    total_available = subscription.credits_remaining + subscription.credits_rollover
    if total_available < amount:
        raise HTTPException(
            status_code=402,  # Payment Required
            detail=f"Insufficient credits. Required: {amount}, Available: {total_available}"
        )
    
    # Deduct credits (prefer using rollover credits first)
    if subscription.credits_rollover >= amount:
        subscription.credits_rollover -= amount
    else:
        remainder = amount - subscription.credits_rollover
        subscription.credits_rollover = 0
        subscription.credits_remaining -= remainder
    
    # Create transaction record
    transaction = models.CreditTransaction(
        user_id=user_id,
        subscription_id=subscription.id,
        amount=-amount,  # Negative for consumption
        transaction_type='usage',
        description=description,
        metadata_json=metadata or {}
    )
    db.add(transaction)
    
    await db.commit()
    await db.refresh(subscription)
    
    return {
        "credits_consumed": amount,
        "credits_remaining": subscription.credits_remaining + subscription.credits_rollover
    }

async def get_credit_cost(operation_type: str, db: AsyncSession) -> int:
    """
    Get the credit cost for a specific operation type from database
    Returns the cost, or raises error if not found
    """
    result = await db.execute(
        select(models.CreditCost).where(
            and_(
                models.CreditCost.operation_type == operation_type,
                models.CreditCost.is_active == True
            )
        )
    )
    credit_cost = result.scalar_one_or_none()
    
    if not credit_cost:
        raise HTTPException(
            status_code=500,
            detail=f"Credit cost configuration not found for operation: {operation_type}"
        )
    
    return credit_cost.cost
