from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from ..db import get_db
from .. import models
from ..services import stripe_service

router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"]
)

@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Stripe webhook events
    """
    # Get the request body and signature header
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")
    
    try:
        # Verify webhook signature
        event = await stripe_service.verify_webhook_signature(payload, sig_header)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Handle different event types
    event_type = event["type"]
    
    if event_type == "checkout.session.completed":
        await handle_checkout_completed(event["data"]["object"], db)
    
    elif event_type == "customer.subscription.created":
        await handle_subscription_created(event["data"]["object"], db)
    
    elif event_type == "customer.subscription.updated":
        await handle_subscription_updated(event["data"]["object"], db)
    
    elif event_type == "customer.subscription.deleted":
        await handle_subscription_deleted(event["data"]["object"], db)
    
    elif event_type == "invoice.payment_succeeded":
        await handle_payment_succeeded(event["data"]["object"], db)
    
    elif event_type == "invoice.payment_failed":
        await handle_payment_failed(event["data"]["object"], db)
    
    elif event_type == "payment_intent.succeeded":
        await handle_payment_intent_succeeded(event["data"]["object"], db)
    
    return {"status": "success"}

async def handle_checkout_completed(session, db: AsyncSession):
    """
    Handle successful checkout session completion
    """
    user_id = int(session["metadata"].get("user_id"))
    plan_name = session["metadata"].get("plan_name")
    billing_cycle = session["metadata"].get("billing_cycle")
    
    # Get user's subscription
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.user_id == user_id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        return
    
    # Get the plan
    plan_result = await db.execute(
        select(models.Plan).where(models.Plan.name == plan_name)
    )
    plan = plan_result.scalar_one_or_none()
    
    if not plan:
        return
    
    # Update subscription
    subscription.plan_id = plan.id
    subscription.billing_cycle = billing_cycle
    subscription.status = "active"
    subscription.stripe_customer_id = session["customer"]
    subscription.stripe_subscription_id = session["subscription"]
    subscription.credits_remaining = plan.credits_per_month
    
    # Create transaction for new credits
    transaction = models.CreditTransaction(
        user_id=user_id,
        subscription_id=subscription.id,
        amount=plan.credits_per_month,
        transaction_type="trial" if session.get("mode") == "trial" else "purchase",
        description=f"Subscription to {plan.display_name} plan",
        metadata_json={"session_id": session["id"]}
    )
    db.add(transaction)
    
    await db.commit()

async def handle_subscription_created(subscription_data, db: AsyncSession):
    """
    Handle new subscription creation
    """
    customer_id = subscription_data["customer"]
    subscription_id = subscription_data["id"]
    
    # Find subscription by Stripe customer ID
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.stripe_customer_id == customer_id)
    )
    subscription = result.scalar_one_or_none()
    
    if subscription:
        subscription.stripe_subscription_id = subscription_id
        subscription.status = "active"
        subscription.current_period_start = datetime.fromtimestamp(subscription_data["current_period_start"])
        subscription.current_period_end = datetime.fromtimestamp(subscription_data["current_period_end"])
        await db.commit()

async def handle_subscription_updated(subscription_data, db: AsyncSession):
    """
    Handle subscription updates (plan changes, renewals)
    """
    subscription_id = subscription_data["id"]
    
    # Find subscription by Stripe subscription ID
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.stripe_subscription_id == subscription_id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        return
    
    # Update period dates
    subscription.current_period_start = datetime.fromtimestamp(subscription_data["current_period_start"])
    subscription.current_period_end = datetime.fromtimestamp(subscription_data["current_period_end"])
    
    # Update status
    subscription.status = subscription_data["status"]
    
    # If subscription is canceled
    if subscription_data.get("cancel_at_period_end"):
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.utcnow()
    
    await db.commit()

async def handle_subscription_deleted(subscription_data, db: AsyncSession):
    """
    Handle subscription cancellation/deletion
    """
    subscription_id = subscription_data["id"]
    
    # Find subscription
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.stripe_subscription_id == subscription_id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        return
    
    # Get free plan
    free_plan_result = await db.execute(
        select(models.Plan).where(models.Plan.name == "free")
    )
    free_plan = free_plan_result.scalar_one()
    
    # Downgrade to free
    subscription.plan_id = free_plan.id
    subscription.status = "active"
    subscription.billing_cycle = None
    subscription.stripe_subscription_id = None
    subscription.credits_remaining = free_plan.credits_per_month
    subscription.cancelled_at = datetime.utcnow()
    
    await db.commit()

async def handle_payment_succeeded(invoice, db: AsyncSession):
    """
    Handle successful payment (renewal, upgrade, etc.)
    """
    customer_id = invoice["customer"]
    subscription_id = invoice.get("subscription")
    
    if not subscription_id:
        return
    
    # Find subscription
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.stripe_subscription_id == subscription_id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        return
    
    # Get plan
    plan_result = await db.execute(
        select(models.Plan).where(models.Plan.id == subscription.plan_id)
    )
    plan = plan_result.scalar_one()
    
    # Refresh credits for new period
    # Handle rollover
    rollover_limit = 100 if plan.name == "pro" else 500 if plan.name == "team" else 0
    if subscription.credits_remaining > 0:
        subscription.credits_rollover = min(subscription.credits_remaining, rollover_limit)
    
    subscription.credits_remaining = plan.credits_per_month
    
    # Create transaction
    transaction = models.CreditTransaction(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        amount=plan.credits_per_month,
        transaction_type="rollover" if subscription.credits_rollover > 0 else "purchase",
        description=f"Monthly credit renewal - {plan.display_name}",
        metadata_json={"invoice_id": invoice["id"]}
    )
    db.add(transaction)
    
    await db.commit()

async def handle_payment_failed(invoice, db: AsyncSession):
    """
    Handle failed payment
    """
    subscription_id = invoice.get("subscription")
    
    if not subscription_id:
        return
    
    # Find subscription
    result = await db.execute(
        select(models.Subscription).where(models.Subscription.stripe_subscription_id == subscription_id)
    )
    subscription = result.scalar_one_or_none()
    
    if subscription:
        subscription.status = "past_due"
        await db.commit()
    
    # TODO: Send email notification to user

async def handle_payment_intent_succeeded(payment_intent, db: AsyncSession):
    """
    Handle successful one-time payment (e.g., credit purchases)
    """
    if payment_intent["metadata"].get("type") == "credit_purchase":
        credits = int(payment_intent["metadata"].get("credits", 0))
        customer_id = payment_intent["customer"]
        
        # Find subscription by customer ID
        result = await db.execute(
            select(models.Subscription).where(models.Subscription.stripe_customer_id == customer_id)
        )
        subscription = result.scalar_one_or_none()
        
        if subscription:
            # Add credits
            subscription.credits_remaining += credits
            
            # Create transaction
            transaction = models.CreditTransaction(
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                amount=credits,
                transaction_type="purchase",
                description=f"Purchased {credits} credits",
                metadata_json={"payment_intent_id": payment_intent["id"]}
            )
            db.add(transaction)
            
            await db.commit()
