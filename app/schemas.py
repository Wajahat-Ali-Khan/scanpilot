from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, Dict, Any, Generic, TypeVar, List
from datetime import datetime

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int

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

class AuditResultResponse(BaseModel):
    id: int
    input_text: Optional[str]
    result_json: Dict[str, Any]
    status: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
    
class UploadWithStatusResponse(BaseModel):
    id: int
    original_filename: str
    file_size: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class ProcessFileRequest(BaseModel):
    upload_id: int

class FileProcessingResponse(BaseModel):
    upload_id: int
    status: str
    message: str
    result_id: Optional[int] = None

# Document Schemas
class DocumentCreate(BaseModel):
    title: str
    content: Optional[str] = ""

class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class DocumentTitleUpdate(BaseModel):
    title: str

class DocumentResponse(BaseModel):
    id: int
    title: str
    content: Optional[str]
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)

# Comment Schemas
class CommentCreate(BaseModel):
    content: str
    position_start: Optional[int] = None
    position_end: Optional[int] = None

class CommentResponse(BaseModel):
    id: int
    document_id: int
    user_id: int
    content: str
    position_start: Optional[int]
    position_end: Optional[int]
    resolved: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# Version Schemas
class DocumentVersionResponse(BaseModel):
    id: int
    document_id: int
    content: str
    created_at: datetime
    created_by: Optional[int]
    created_by_email: Optional[str] = None
    created_by_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

# Collaborator Schemas
class CollaboratorInvite(BaseModel):
    email: EmailStr
    role: str = "editor"  # viewer, editor

class CollaboratorResponse(BaseModel):
    id: int
    document_id: int
    user_id: int
    role: str
    invited_by: Optional[int]
    created_at: datetime
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class CollaboratorUpdate(BaseModel):
    role: str  # viewer, editor

# ===== SUBSCRIPTION SCHEMAS =====

# Plan Schemas
class PlanResponse(BaseModel):
    id: int
    name: str
    display_name: str
    price_monthly: float
    price_yearly: float
    credits_per_month: int
    max_collaborators: int
    max_file_size_mb: int
    max_documents: Optional[int]
    features_json: Dict[str, Any]
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)

# Subscription Schemas
class SubscriptionResponse(BaseModel):
    id: int
    user_id: int
    plan_id: int
    plan: PlanResponse
    status: str
    billing_cycle: Optional[str]
    credits_remaining: int
    credits_rollover: int
    trial_ends_at: Optional[datetime]
    current_period_start: datetime
    current_period_end: Optional[datetime]
    cancelled_at: Optional[datetime]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class SubscriptionUpgradeRequest(BaseModel):
    plan_name: str  # "pro", "team", "enterprise"
    billing_cycle: str = "monthly"  # "monthly" or "yearly"

class SubscriptionCancelRequest(BaseModel):
    reason: Optional[str] = None
    immediate: bool = False  #If True, cancel immediately. If False, cancel at period end

# Credit Schemas
class CreditBalance(BaseModel):
    credits_remaining: int
    credits_rollover: int
    total_credits: int
    plan_credits_per_month: int
    next_renewal_date: Optional[datetime]

class CreditTransactionResponse(BaseModel):
    id: int
    amount: int
    transaction_type: str
    description: str
    metadata_json: Optional[Dict[str, Any]]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class CreditPurchaseRequest(BaseModel):
    amount: int = Field(..., ge=1, description="Number of credit packs to purchase")

class ConsumeCreditsRequest(BaseModel):
    amount: int = Field(..., ge=1)
    operation_type: str  # "analysis", "document_process", etc.
    metadata: Optional[Dict[str, Any]] = None

# Referral Schemas
class ReferralResponse(BaseModel):
    id: int
    referral_code: str
    status: str
    bonus_credits: int
    created_at: datetime
    completed_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)

class ReferralStatsResponse(BaseModel):
    referral_code: str
    total_referrals: int
    successful_referrals: int
    pending_referrals: int
    total_credits_earned: int

class ApplyReferralRequest(BaseModel):
    referral_code: str

# Usage Stats Schemas
class UsageStatsResponse(BaseModel):
    current_period_start: datetime
    current_period_end: datetime
    credits_used: int
    credits_remaining: int
    total_credits_allocated: int
    usage_percentage: float
    top_operations: list[Dict[str, Any]]

# Credit Cost Schemas
class CreditCostResponse(BaseModel):
    id: int
    operation_type: str
    cost: int
    description: Optional[str]
    is_active: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class CreditCostUpdate(BaseModel):
    cost: int = Field(..., ge=0, description="Credit cost (must be >= 0)")
    description: Optional[str] = None
    is_active: Optional[bool] = None