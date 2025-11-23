"""
Subscription middleware and decorators for enforcing plan limits
"""
from functools import wraps
from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Callable, Optional

from ..db import get_db
from .. import models
from ..auth import get_current_user

def require_plan(min_plan: str = "free"):
    """
    Decorator to require minimum subscription plan
    Usage: @require_plan(min_plan="pro")
    """
    plan_hierarchy = {"free": 0, "pro": 1, "team": 2, "enterprise": 3}
    
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract db and current_user from kwargs
            db: AsyncSession = kwargs.get("db")
            current_user: models.User = kwargs.get("current_user")
            
            if not db or not current_user:
                raise HTTPException(status_code=500, detail="Missing required dependencies")
            
            # Get user's subscription
            result = await db.execute(
                select(models.Subscription, models.Plan)
                .join(models.Plan, models.Subscription.plan_id == models.Plan.id)
                .where(models.Subscription.user_id == current_user.id)
            )
            row = result.first()
            
            if not row:
                raise HTTPException(
                    status_code=403,
                    detail="No active subscription found"
                )
            
            subscription, plan = row
            
            # Check if user's plan meets minimum requirement
            user_plan_level = plan_hierarchy.get(plan.name, 0)
            required_level = plan_hierarchy.get(min_plan, 0)
            
            if user_plan_level < required_level:
                raise HTTPException(
                    status_code=402,  # Payment Required
                    detail=f"This feature requires {min_plan.capitalize()} plan or higher. Please upgrade your subscription."
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

def consume_credits(amount: int, operation_type: str, description: str = None):
    """
    Decorator to automatically consume credits for an operation
    Usage: @consume_credits(amount=2, operation_type="document_analysis")
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            db: AsyncSession = kwargs.get("db")
            current_user: models.User = kwargs.get("current_user")
            
            if not db or not current_user:
                raise HTTPException(status_code=500, detail="Missing required dependencies")
            
            # Get user's subscription
            result = await db.execute(
                select(models.Subscription, models.Plan)
                .join(models.Plan, models.Subscription.plan_id == models.Plan.id)
                .where(models.Subscription.user_id == current_user.id)
            )
            row = result.first()
            
            if not row:
                raise HTTPException(status_code=403, detail="No active subscription")
            
            subscription, plan = row
            
            # Check if plan has unlimited credits (enterprise)
            if plan.credits_per_month == -1:
                # Execute function without consuming credits
                return await func(*args, **kwargs)
            
            # Check credit availability
            total_available = subscription.credits_remaining + subscription.credits_rollover
            
            if total_available < amount:
                raise HTTPException(
                    status_code=402,
                    detail=f"Insufficient credits. Required: {amount}, Available: {total_available}. Please purchase more credits or upgrade your plan."
                )
            
            # Deduct credits (prefer rollover first)
            if subscription.credits_rollover >= amount:
                subscription.credits_rollover -= amount
            else:
                remainder = amount - subscription.credits_rollover
                subscription.credits_rollover = 0
                subscription.credits_remaining -= remainder
            
            # Create transaction record
            transaction = models.CreditTransaction(
                user_id=current_user.id,
                subscription_id=subscription.id,
                amount=-amount,
                transaction_type="usage",
                description=description or f"{operation_type} operation",
                metadata_json={"operation_type": operation_type}
            )
            db.add(transaction)
            
            # Execute the function
            result = await func(*args, **kwargs)
            
            # Commit after successful execution
            await db.commit()
            await db.refresh(subscription)
            
            return result
        
        return wrapper
    return decorator

def check_feature(feature_name: str):
    """
    Decorator to check if user's plan includes a specific feature
    Usage: @check_feature(feature="api_access")
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            db: AsyncSession = kwargs.get("db")
            current_user: models.User = kwargs.get("current_user")
            
            if not db or not current_user:
                raise HTTPException(status_code=500, detail="Missing required dependencies")
            
            # Get user's plan
            result = await db.execute(
                select(models.Subscription, models.Plan)
                .join(models.Plan, models.Subscription.plan_id == models.Plan.id)
                .where(models.Subscription.user_id == current_user.id)
            )
            row = result.first()
            
            if not row:
                raise HTTPException(status_code=403, detail="No active subscription")
            
            subscription, plan = row
            
            # Check if feature is in plan
            features = plan.features_json or {}
            
            if feature_name not in features or not features[feature_name]:
                raise HTTPException(
                    status_code=402,
                    detail=f"'{feature_name}' is not available in your current plan. Please upgrade to access this feature."
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

async def check_file_size_limit(
    file_size: int,
    current_user: models.User,
    db: AsyncSession
) -> bool:
    """
    Check if file size is within user's plan limit
    """
    result = await db.execute(
        select(models.Subscription, models.Plan)
        .join(models.Plan, models.Subscription.plan_id == models.Plan.id)
        .where(models.Subscription.user_id == current_user.id)
    )
    row = result.first()
    
    if not row:
        return False
    
    subscription, plan = row
    
    # Convert to MB
    file_size_mb = file_size / (1024 * 1024)
    
    # Check limit (-1 means unlimited)
    if plan.max_file_size_mb != -1 and file_size_mb > plan.max_file_size_mb:
        raise HTTPException(
            status_code=413,  # Request Entity Too Large
            detail=f"File size ({file_size_mb:.2f}MB) exceeds your plan limit ({plan.max_file_size_mb}MB). Please upgrade to upload larger files."
        )
    
    return True

async def check_document_limit(
    current_user: models.User,
    db: AsyncSession
) -> bool:
    """
    Check if user has reached document limit
    """
    result = await db.execute(
        select(models.Subscription, models.Plan)
        .join(models.Plan, models.Subscription.plan_id == models.Plan.id)
        .where(models.Subscription.user_id == current_user.id)
    )
    row = result.first()
    
    if not row:
        return False
    
    subscription, plan = row
    
    # Check if plan has unlimited documents
    if plan.max_documents is None or plan.max_documents == -1:
        return True
    
    # Count user's documents
    count_result = await db.execute(
        select(models.Document).where(models.Document.owner_id == current_user.id)
    )
    doc_count = len(count_result.scalars().all())
    
    if doc_count >= plan.max_documents:
        raise HTTPException(
            status_code=402,
            detail=f"Document limit reached ({doc_count}/{plan.max_documents}). Please upgrade your plan or delete old documents."
        )
    
    return True

async def check_collaborator_limit(
    document_id: int,
    current_user: models.User,
    db: AsyncSession
) -> bool:
    """
    Check if document has reached collaborator limit
    """
    # Get document to find owner
    doc_result = await db.execute(
        select(models.Document).where(models.Document.id == document_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        return False
    
    # Get document owner's subscription
    result = await db.execute(
        select(models.Subscription, models.Plan)
        .join(models.Plan, models.Subscription.plan_id == models.Plan.id)
        .where(models.Subscription.user_id == doc.owner_id)
    )
    row = result.first()
    
    if not row:
        return False
    
    subscription, plan = row
    
    # Check if plan has unlimited collaborators
    if plan.max_collaborators == -1:
        return True
    
    # Count current collaborators (excluding owner)
    collaborator_result = await db.execute(
        select(models.DocumentCollaborator)
        .where(models.DocumentCollaborator.document_id == document_id)
    )
    collaborator_count = len(collaborator_result.scalars().all())
    
    if collaborator_count >= plan.max_collaborators:
        raise HTTPException(
            status_code=402,
            detail=f"Collaborator limit reached ({collaborator_count}/{plan.max_collaborators}). Upgrade to add more collaborators."
        )
    
    return True
