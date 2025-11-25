from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pathlib import Path

from ..db import get_db
from .. import models, schemas
from app.auth import get_current_user

router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
    dependencies=[Depends(get_current_user)]
)

@router.post("/run-migration")
async def run_migration(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Run the subscription system database migration
    WARNING: This should only be run once!
    """
    # TODO: Add admin role check here
    # For now, any authenticated user can run this (NOT suitable for production)
    
    migration_file = Path(__file__).parent.parent.parent / 'migrations' / '001_add_subscription_system.sql'
    
    if not migration_file.exists():
        raise HTTPException(status_code=404, detail="Migration file not found")
    
    try:
        with open(migration_file, 'r') as f:
            sql = f.read()
        
        # Split by semicolon and execute each statement
        statements = [s.strip() for s in sql.split(';') if s.strip() and not s.strip().startswith('--')]
        
        executed = []
        for statement in statements:
            if statement and 'DO $$' not in statement:  # Skip DO blocks for now
                try:
                    await db.execute(text(statement))
                    executed.append(statement[:50] + "...")
                except Exception as e:
                    # Log but continue (some statements may already be executed)
                    print(f"Statement warning: {e}")
        
        await db.commit()
        
        return {
            "message": "Migration completed",
            "statements_executed": len(executed),
            "note": "Check database to verify tables were created"
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")

@router.post("/users/{user_id}/grant-credits")
async def grant_credits(
    user_id: int,
    amount: int,
    reason: str = "Manual grant by admin",
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Manually grant credits to a user"""
    # TODO: Add admin role check
    
    from sqlalchemy import select
    
    # Get user's subscription
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == user_id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="User subscription not found")
    
    # Add credits
    subscription.credits_remaining += amount
    
    # Create transaction record
    transaction = models.CreditTransaction(
        user_id=user_id,
        subscription_id=subscription.id,
        amount=amount,
        transaction_type="bonus",
        description=reason,
        metadata_json={"granted_by": current_user.id}
    )
    db.add(transaction)
    
    await db.commit()
    
    return {
        "message": f"Granted {amount} credits to user {user_id}",
        "new_balance": subscription.credits_remaining + subscription.credits_rollover
    }

@router.get("/analytics")
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get subscription analytics"""
    # TODO: Add admin role check
    
    from sqlalchemy import select, func
    
    # Count subscriptions by plan
    subs_by_plan = await db.execute(
        select(
            models.Plan.name,
            models.Plan.display_name,
            func.count(models.Subscription.id).label('count')
        )
        .join(models.Subscription, models.Plan.id == models.Subscription.plan_id)
        .group_by(models.Plan.id, models.Plan.name, models.Plan.display_name)
    )
    
    plan_stats = [
        {"plan": row.name, "display_name": row.display_name, "subscribers": row.count}
        for row in subs_by_plan.all()
    ]
    
    # Total users
    total_users_result = await db.execute(select(func.count(models.User.id)))
    total_users = total_users_result.scalar()
    
    # Total subscriptions
    total_subs_result = await db.execute(select(func.count(models.Subscription.id)))
    total_subs = total_subs_result.scalar()
    
    return {
        "total_users": total_users,
        "total_subscriptions": total_subs,
        "subscriptions_by_plan": plan_stats,
        "note": "More analytics coming soon (MRR, ARR, churn rate, etc.)"
    }

# ===== CREDIT COST MANAGEMENT =====

@router.get("/credit-costs", response_model=list)
async def get_all_credit_costs(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all credit cost configurations"""
    # TODO: Add admin role check
    
    from sqlalchemy import select
    
    result = await db.execute(
        select(models.CreditCost).order_by(models.CreditCost.operation_type)
    )
    costs = result.scalars().all()
    
    return [schemas.CreditCostResponse.model_validate(cost) for cost in costs]

@router.get("/credit-costs/{operation_type}")
async def get_credit_cost(
    operation_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get credit cost for a specific operation"""
    # TODO: Add admin role check
    
    from sqlalchemy import select
    
    result = await db.execute(
        select(models.CreditCost).where(models.CreditCost.operation_type == operation_type)
    )
    cost = result.scalar_one_or_none()
    
    if not cost:
        raise HTTPException(status_code=404, detail=f"Credit cost not found for: {operation_type}")
    
    return schemas.CreditCostResponse.model_validate(cost)

@router.put("/credit-costs/{operation_type}")
async def update_credit_cost(
    operation_type: str,
    update_data: schemas.CreditCostUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Update credit cost for an operation"""
    # TODO: Add admin role check
    
    from sqlalchemy import select
    
    result = await db.execute(
        select(models.CreditCost).where(models.CreditCost.operation_type == operation_type)
    )
    cost = result.scalar_one_or_none()
    
    if not cost:
        raise HTTPException(status_code=404, detail=f"Credit cost not found for: {operation_type}")
    
    # Update fields
    cost.cost = update_data.cost
    if update_data.description is not None:
        cost.description = update_data.description
    if update_data.is_active is not None:
        cost.is_active = update_data.is_active
    
    await db.commit()
    await db.refresh(cost)
    
    return {
        "message": f"Credit cost updated for {operation_type}",
        "cost": schemas.CreditCostResponse.model_validate(cost)
    }

