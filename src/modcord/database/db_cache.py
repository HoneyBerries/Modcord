"""
Query result caching for database operations.

Provides a simple TTL-based cache for database query results
to reduce repeated database access for frequently queried data.
"""

from typing import Dict, Tuple, Any, Optional
import time

from modcord.util.logger import get_logger

logger = get_logger("database_cache")


class DatabaseQueryCache:
    """
    TTL-based cache for database query results.
    
    Caches query results with timestamps and automatically expires
    entries after a configured TTL (time-to-live) period.
    """
    
    def __init__(self, ttl_seconds: int = 60):
        """
        Initialize the query cache.
        
        Args:
            ttl_seconds: Time-to-live in seconds for cached entries (default: 60)
        """
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._ttl_seconds = ttl_seconds
    
    def get(self, cache_key: str) -> Optional[Any]:
        """
        Get a cached query result if still valid.
        
        Args:
            cache_key: Unique identifier for the cached query
        
        Returns:
            Cached result if valid, None if expired or not found
        """
        if cache_key in self._cache:
            timestamp, result = self._cache[cache_key]
            if time.time() - timestamp < self._ttl_seconds:
                logger.debug("[CACHE] Hit for key: %s", cache_key)
                return result
            else:
                # Cache expired, remove it
                del self._cache[cache_key]
                logger.debug("[CACHE] Expired key: %s", cache_key)
        return None
    
    def set(self, cache_key: str, result: Any) -> None:
        """
        Cache a query result with current timestamp.
        
        Args:
            cache_key: Unique identifier for the query
            result: Query result to cache
        """
        self._cache[cache_key] = (time.time(), result)
        logger.debug("[CACHE] Set key: %s", cache_key)
    
    def invalidate(self, pattern: Optional[str] = None) -> int:
        """
        Invalidate cache entries matching a pattern.
        
        Args:
            pattern: String pattern to match in cache keys.
                    If None, clears all cache entries.
        
        Returns:
            Number of entries invalidated
        """
        if pattern is None:
            count = len(self._cache)
            self._cache.clear()
            logger.debug("[CACHE] Cleared all %d entries", count)
            return count
        else:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
            logger.debug("[CACHE] Cleared %d entries matching '%s'", len(keys_to_delete), pattern)
            return len(keys_to_delete)
    
    def get_db_cache_stats(self) -> Dict[str, int]:
        """
        Get statistics for the database query cache.
        
        Returns:
            Dictionary with cache size and other metrics
        """
        return {
            'size': len(self._cache),
            'ttl_seconds': self._ttl_seconds
        }