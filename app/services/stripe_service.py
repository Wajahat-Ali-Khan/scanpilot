"""
Stripe integration service for payment processing
"""
import stripe
import os
from datetime import datetime, timedelta
from typing import Optional

# Initialize Stripe with secret key from environment
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# Get publishable key for frontend
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

# Webhook secret for verifying signatures
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Your domain for redirects
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

async def create_customer(user_email: str, user_name: Optional[str] = None, user_id: int = None) -> stripe.Customer:
    """
    Create a Stripe customer
    """
    try:
        customer = stripe.Customer.create(
            email=user_email,
            name=user_name or user_email,
            metadata={"user_id": str(user_id)} if user_id else {}
        )
        return customer
    except stripe.error.StripeError as e:
        raise Exception(f"Failed to create Stripe customer: {str(e)}")

async def create_checkout_session(
    customer_id: str,
    plan_name: str,
    price_monthly: float,
    price_yearly: float,
    billing_cycle: str = "monthly",
    user_id: int = None
) -> dict:
    """
    Create a Stripe checkout session for subscription
    """
    try:
        # Determine price based on billing cycle
        unit_amount = int(price_monthly * 100) if billing_cycle == "monthly" else int(price_yearly * 100)
        interval = "month" if billing_cycle == "monthly" else "year"
        
        # Create or get price
        price = stripe.Price.create(
            unit_amount=unit_amount,
            currency="usd",
            recurring={"interval": interval},
            product_data={
                "name": f"ScanPilot {plan_name.capitalize()} Plan",
                "description": f"{plan_name.capitalize()} subscription - billed {billing_cycle}"
            },
        )
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price": price.id,
                "quantity": 1,
            }],
            mode="subscription",
            success_url=f"{FRONTEND_URL}/subscription/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/pricing?canceled=true",
            metadata={
                "user_id": str(user_id),
                "plan_name": plan_name,
                "billing_cycle": billing_cycle
            }
        )
        
        return {
            "session_id": session.id,
            "checkout_url": session.url,
            "publishable_key": STRIPE_PUBLISHABLE_KEY
        }
        
    except stripe.error.StripeError as e:
        raise Exception(f"Failed to create checkout session: {str(e)}")

async def create_subscription(
    customer_id: str,
    price_id: str,
    trial_days: int = 0
) -> stripe.Subscription:
    """
    Create a Stripe subscription directly (without checkout)
    """
    try:
        subscription_params = {
            "customer": customer_id,
            "items": [{"price": price_id}],
        }
        
        if trial_days > 0:
            subscription_params["trial_period_days"] = trial_days
        
        subscription = stripe.Subscription.create(**subscription_params)
        return subscription
        
    except stripe.error.StripeError as e:
        raise Exception(f"Failed to create subscription: {str(e)}")

async def update_subscription(
    subscription_id: str,
    new_price_id: str
) -> stripe.Subscription:
    """
    Update an existing subscription (upgrade/downgrade)
    """
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        
        updated_subscription = stripe.Subscription.modify(
            subscription_id,
            items=[{
                "id": subscription["items"]["data"][0].id,
                "price": new_price_id,
            }],
            proration_behavior="always_invoice",
        )
        
        return updated_subscription
        
    except stripe.error.StripeError as e:
        raise Exception(f"Failed to update subscription: {str(e)}")

async def cancel_subscription(
    subscription_id: str,
    immediate: bool = False
) -> stripe.Subscription:
    """
    Cancel a Stripe subscription
    """
    try:
        if immediate:
            # Cancel immediately
            subscription = stripe.Subscription.cancel(subscription_id)
        else:
            # Cancel at period end
            subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
        
        return subscription
        
    except stripe.error.StripeError as e:
        raise Exception(f"Failed to cancel subscription: {str(e)}")

async def create_payment_intent_for_credits(
    customer_id: str,
    amount_cents: int,
    credits: int
) -> dict:
    """
    Create a one-time payment for credit packs
    """
    try:
        payment_intent = stripe.PaymentIntent.create(
            customer=customer_id,
            amount=amount_cents,
            currency="usd",
            payment_method_types=["card"],
            metadata={
                "type": "credit_purchase",
                "credits": str(credits)
            }
        )
        
        return {
            "client_secret": payment_intent.client_secret,
            "publishable_key": STRIPE_PUBLISHABLE_KEY
        }
        
    except stripe.error.StripeError as e:
        raise Exception(f"Failed to create payment intent: {str(e)}")

async def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """
    Verify Stripe webhook signature and return event
    """
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
        return event
    except ValueError as e:
        raise Exception(f"Invalid payload: {str(e)}")
    except stripe.error.SignatureVerificationError as e:
        raise Exception(f"Invalid signature: {str(e)}")

def get_subscription_period_end(subscription: stripe.Subscription) -> datetime:
    """
    Extract period end from Stripe subscription
    """
    return datetime.fromtimestamp(subscription.current_period_end)

def get_subscription_period_start(subscription: stripe.Subscription) -> datetime:
    """
    Extract period start from Stripe subscription
    """
    return datetime.fromtimestamp(subscription.current_period_start)
