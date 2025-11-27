# Cache module initialization
from .redis_cache import Cache, get_redis, close_redis, cache_result, invalidate_cache

__all__ = ['Cache', 'get_redis', 'close_redis', 'cache_result', 'invalidate_cache']
