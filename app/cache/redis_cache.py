"""
Redis cache configuration and utilities.

Provides caching functionality for frequently accessed data
to improve application performance.
"""

from typing import Optional, Any, Callable
from functools import wraps
import json
import redis.asyncio as redis
from app.config import settings


# Redis client instance
redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """
    Get Redis client instance.
    
    Returns:
        Redis client
    """
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(
            settings.REDIS_URL if hasattr(settings, 'REDIS_URL') else "redis://localhost:6379",
            encoding="utf-8",
            decode_responses=True
        )
    return redis_client


async def close_redis() -> None:
    """Close Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None


class Cache:
    """Cache utility class for Redis operations."""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        value = await self.redis.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 3600
    ) -> bool:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default: 1 hour)
            
        Returns:
            True if successful
        """
        try:
            serialized = json.dumps(value) if not isinstance(value, str) else value
            return await self.redis.setex(key, ttl, serialized)
        except (TypeError, ValueError):
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted
        """
        return await self.redis.delete(key) > 0
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.
        
        Args:
            pattern: Key pattern (e.g., "user:*")
            
        Returns:
            Number of keys deleted
        """
        keys = []
        async for key in self.redis.scan_iter(match=pattern):
            keys.append(key)
        
        if keys:
            return await self.redis.delete(*keys)
        return 0
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists
        """
        return await self.redis.exists(key) > 0


def cache_result(
    key_prefix: str,
    ttl: int = 3600,
    key_builder: Optional[Callable] = None
):
    """
    Decorator to cache function results.
    
    Args:
        key_prefix: Prefix for cache key
        ttl: Time to live in seconds
        key_builder: Optional function to build cache key from args
        
    Example:
        @cache_result("user", ttl=300)
        async def get_user(user_id: int):
            # Expensive operation
            return user
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key
            if key_builder:
                cache_key = f"{key_prefix}:{key_builder(*args, **kwargs)}"
            else:
                # Default: use first argument as key
                cache_key = f"{key_prefix}:{args[0]}" if args else key_prefix
            
            # Try to get from cache
            redis_instance = await get_redis()
            cache = Cache(redis_instance)
            cached_value = await cache.get(cache_key)
            
            if cached_value is not None:
                return cached_value
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


async def invalidate_cache(pattern: str) -> int:
    """
    Invalidate all cache keys matching a pattern.
    
    Args:
        pattern: Key pattern to invalidate
        
    Returns:
        Number of keys invalidated
    """
    redis_instance = await get_redis()
    cache = Cache(redis_instance)
    return await cache.delete_pattern(pattern)
