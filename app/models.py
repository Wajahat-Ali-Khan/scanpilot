from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, JSON
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