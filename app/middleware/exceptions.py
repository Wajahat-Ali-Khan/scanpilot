"""
Custom exceptions for the application.

These exceptions provide structured error handling with appropriate
HTTP status codes and error messages.
"""

from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base exception for application errors."""
    
    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class DocumentNotFoundException(AppException):
    """Raised when a document is not found."""
    
    def __init__(self, doc_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {doc_id} not found"
        )


class UploadNotFoundException(AppException):
    """Raised when an upload is not found."""
    
    def __init__(self, upload_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload with ID {upload_id} not found"
        )


class UnauthorizedException(AppException):
    """Raised when user is not authorized."""
    
    def __init__(self, detail: str = "Not authorized to perform this action"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


class InsufficientCreditsException(AppException):
    """Raised when user has insufficient credits."""
    
    def __init__(self, required: int, available: int):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Required: {required}, Available: {available}"
        )


class ValidationException(AppException):
    """Raised when validation fails."""
    
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail
        )


class QuotaExceededException(AppException):
    """Raised when user exceeds quota limits."""
    
    def __init__(self, resource: str, limit: int):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"{resource} limit exceeded. Maximum: {limit}"
        )
