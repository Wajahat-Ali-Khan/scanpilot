from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, JSON, Boolean, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, unique=True, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Upload(Base):
    __tablename__ = "uploads"
    id = Column(Integer, unique=True, primary_key=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String, nullable=True)
    original_filename = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String, nullable=True)
    status = Column(String, default="pending", nullable=False)
    error_message = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now()) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditResult(Base):
    __tablename__ = "audit_results"
    id = Column(Integer, unique=True, primary_key=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    upload_id = Column(ForeignKey("uploads.id", ondelete="SET NULL"), nullable=True)
    input_text = Column(Text, nullable=True)
    result_json = Column(JSON, nullable=False)
    status = Column(String, default="completed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, unique=True, primary_key=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    owner_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id = Column(Integer, unique=True, primary_key=True)
    document_id = Column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, unique=True, primary_key=True)
    document_id = Column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    position_start = Column(Integer, nullable=True)
    position_end = Column(Integer, nullable=True)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DocumentCollaborator(Base):
    __tablename__ = "document_collaborators"
    id = Column(Integer, unique=True, primary_key=True)
    document_id = Column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False, default="viewer")  # viewer, editor, owner
    invited_by = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", backref="collaborators")
    user = relationship("User", foreign_keys=[user_id])
    inviter = relationship("User", foreign_keys=[invited_by])

# ===== SUBSCRIPTION MODELS =====

class Plan(Base):
    """Subscription plan definitions (Free, Pro, Team, Enterprise)"""
    __tablename__ = "plans"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)  # "free", "pro", "team", "enterprise"
    display_name = Column(String, nullable=False)  # "Explorer", "Creator", "Collaborator", "Organization"
    price_monthly = Column(Numeric(10, 2), nullable=False, default=0)
    stripe_price_id_monthly = Column(String, nullable=True)
    price_yearly = Column(Numeric(10, 2), nullable=False, default=0)
    stripe_price_id_yearly = Column(String, nullable=True)
    credits_per_month = Column(Integer, nullable=False)
    max_collaborators = Column(Integer, nullable=False)
    max_file_size_mb = Column(Integer, nullable=False)
    max_documents = Column(Integer, nullable=True)  # NULL = unlimited
    features_json = Column(JSON, nullable=False, default={})  # Flexible feature flags
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Subscription(Base):
    """User subscription tracking"""
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    status = Column(String, nullable=False, default="active")  # active, cancelled, expired, trial, past_due
    billing_cycle = Column(String, nullable=True)  # monthly, yearly, null for free
    credits_remaining = Column(Integer, default=0)
    credits_rollover = Column(Integer, default=0)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    current_period_start = Column(DateTime(timezone=True), server_default=func.now())
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", backref="subscription")
    plan = relationship("Plan")

class CreditTransaction(Base):
    """Credit usage and purchase history"""
    __tablename__ = "credit_transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=True)
    amount = Column(Integer, nullable=False)  # Positive for credits added, negative for used
    transaction_type = Column(String, nullable=False)  # usage, purchase, bonus, refund, trial, rollover, signup
    description = Column(String, nullable=False)
    metadata_json = Column(JSON, nullable=True)  # Store details like document_id, analysis_type, referral_id
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User")
    subscription = relationship("Subscription")

class Referral(Base):
    """Referral tracking and rewards"""
    __tablename__ = "referrals"
    
    id = Column(Integer, primary_key=True)
    referrer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    referee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    referral_code = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default="pending")  # pending, completed, rewarded
    bonus_credits = Column(Integer, default=50)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    referrer = relationship("User", foreign_keys=[referrer_id])
    referee = relationship("User", foreign_keys=[referee_id])

class CreditCost(Base):
    """Configurable credit costs for different operations"""
    __tablename__ = "credit_costs"
    
    id = Column(Integer, primary_key=True)
    operation_type = Column(String, unique=True, nullable=False, index=True)  # file_processing, document_creation, ai_suggestion
    cost = Column(Integer, nullable=False)  # Number of credits required
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())