"""
Error handling middleware for the application.

Provides centralized error handling with structured error responses
and logging.
"""

import logging
from typing import Callable
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.exceptions import AppException

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware for centralized error handling."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and handle any errors.
        
        Args:
            request: The incoming request
            call_next: The next middleware or route handler
            
        Returns:
            Response
        """
        try:
            response = await call_next(request)
            return response
        except AppException as exc:
            # Application-specific exceptions
            logger.warning(
                f"Application error: {exc.detail}",
                extra={
                    "status_code": exc.status_code,
                    "path": request.url.path,
                    "method": request.method
                }
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail}
            )
        except SQLAlchemyError as exc:
            # Database errors
            logger.error(
                f"Database error: {str(exc)}",
                extra={
                    "path": request.url.path,
                    "method": request.method
                },
                exc_info=True
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Database error occurred"}
            )
        except Exception as exc:
            # Unexpected errors
            logger.error(
                f"Unexpected error: {str(exc)}",
                extra={
                    "path": request.url.path,
                    "method": request.method
                },
                exc_info=True
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"}
            )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    Handle validation errors.
    
    Args:
        request: The incoming request
        exc: The validation error
        
    Returns:
        JSON response with validation errors
    """
    logger.warning(
        f"Validation error: {exc.errors()}",
        extra={
            "path": request.url.path,
            "method": request.method
        }
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": exc.errors()
        }
    )
