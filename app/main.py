from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
from .config import settings
from .db import init_db
from .cache import get_redis, close_redis
from .middleware.error_handler import ErrorHandlerMiddleware, validation_exception_handler
from .api import auth, users, uploads, results, documents, ws, subscriptions, credits, referrals, admin, webhooks, collaborators, search
import os

# Create uploads directory
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    # Initialize Redis connection
    try:
        await get_redis()
        print("✅ Redis connection established")
    except Exception as e:
        print(f"⚠️  Redis connection failed: {e}")
        print("   Application will continue without caching")
    
    yield
    
    # Shutdown
    await close_redis()
    print("✅ Redis connection closed")

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="ScanPilot API",
    description="Secure, scalable SaaS backend for document analysis",
    version="1.0.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Add error handling middleware
app.add_middleware(ErrorHandlerMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(uploads.router)
app.include_router(results.router)
app.include_router(documents.router)
app.include_router(collaborators.router)
app.include_router(ws.router)
app.include_router(search.router)

# Subscription system routers
app.include_router(subscriptions.router)
app.include_router(credits.router)
app.include_router(referrals.router)
app.include_router(admin.router)

# Webhooks (no auth dependency)
app.include_router(webhooks.router)

@app.get("/")
@limiter.limit("10/minute")
async def root(request: Request):
    return {
        "message": "ScanPilot API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)