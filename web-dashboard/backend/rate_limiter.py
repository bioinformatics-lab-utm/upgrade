"""
Rate Limiter for Sanic API
Provides Redis-based rate limiting to prevent abuse and DDoS attacks

Usage:
    from rate_limiter import RateLimiter, rate_limit

    limiter = RateLimiter(app)
    
    @app.route('/api/login', methods=['POST'])
    @rate_limit("5/minute")
    async def login(request):
        ...
"""
import time
import functools
from collections import defaultdict
from typing import Optional, Callable
from sanic import Sanic
from sanic.response import json
from sanic.request import Request
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Redis-based rate limiter with fallback to in-memory storage
    
    Supports rate limits in format:
    - "5/minute" - 5 requests per minute
    - "100/hour" - 100 requests per hour
    - "1000/day" - 1000 requests per day
    """
    
    # Time multipliers in seconds
    TIME_UNITS = {
        'second': 1,
        'minute': 60,
        'hour': 3600,
        'day': 86400
    }
    
    def __init__(self, app: Optional[Sanic] = None):
        self.app = app
        self._memory_storage = defaultdict(list)  # Fallback in-memory storage
        self._cleanup_interval = 300  # Clean up old entries every 5 minutes
        self._last_cleanup = time.time()
        
        if app:
            self.init_app(app)
    
    def init_app(self, app: Sanic):
        """Initialize with Sanic app"""
        self.app = app
        app.ctx.rate_limiter = self
        logger.info("Rate limiter initialized")
    
    def parse_rate(self, rate_string: str) -> tuple[int, int]:
        """
        Parse rate string like "5/minute" to (count, seconds)
        
        Returns:
            (requests_allowed, time_window_seconds)
        """
        try:
            count, unit = rate_string.lower().replace(' ', '').split('/')
            count = int(count)
            
            # Handle plural units
            unit = unit.rstrip('s')
            
            if unit not in self.TIME_UNITS:
                raise ValueError(f"Unknown time unit: {unit}")
            
            return count, self.TIME_UNITS[unit]
        except Exception as e:
            logger.error(f"Failed to parse rate string '{rate_string}': {e}")
            return 100, 60  # Default: 100/minute
    
    def get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, handling proxies"""
        # Check for forwarded headers (behind reverse proxy)
        forwarded_for = request.headers.get('X-Forwarded-For', '')
        if forwarded_for:
            # Take the first IP in the chain (original client)
            return forwarded_for.split(',')[0].strip()
        
        real_ip = request.headers.get('X-Real-IP', '')
        if real_ip:
            return real_ip.strip()
        
        # Direct connection
        return request.ip or 'unknown'
    
    async def is_rate_limited(
        self, 
        key: str, 
        limit: int, 
        window: int
    ) -> tuple[bool, dict]:
        """
        Check if request should be rate limited
        
        Args:
            key: Unique identifier (e.g., "login:192.168.1.1")
            limit: Max requests allowed
            window: Time window in seconds
            
        Returns:
            (is_limited, rate_info)
        """
        now = time.time()
        window_start = now - window
        
        # Try Redis first
        redis = getattr(self.app.ctx, 'redis', None) if self.app else None
        
        if redis:
            try:
                return await self._check_redis(redis, key, limit, window, now)
            except Exception as e:
                logger.warning(f"Redis rate limit check failed, using memory: {e}")
        
        # Fallback to in-memory
        return self._check_memory(key, limit, window, now, window_start)
    
    async def _check_redis(
        self, 
        redis, 
        key: str, 
        limit: int, 
        window: int,
        now: float
    ) -> tuple[bool, dict]:
        """Check rate limit using Redis sorted sets"""
        redis_key = f"ratelimit:{key}"
        
        # Use pipeline for atomic operations
        pipe = redis.pipeline()
        
        # Remove old entries outside window
        pipe.zremrangebyscore(redis_key, 0, now - window)
        
        # Count current requests in window
        pipe.zcard(redis_key)
        
        # Add current request
        pipe.zadd(redis_key, {str(now): now})
        
        # Set expiry to prevent memory leaks
        pipe.expire(redis_key, window + 1)
        
        results = await pipe.execute()
        current_count = results[1]
        
        remaining = max(0, limit - current_count - 1)
        reset_time = int(now + window)
        
        rate_info = {
            'limit': limit,
            'remaining': remaining,
            'reset': reset_time,
            'window': window
        }
        
        if current_count >= limit:
            return True, rate_info
        
        return False, rate_info
    
    def _check_memory(
        self, 
        key: str, 
        limit: int, 
        window: int,
        now: float,
        window_start: float
    ) -> tuple[bool, dict]:
        """Check rate limit using in-memory storage"""
        # Periodic cleanup
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup_memory()
            self._last_cleanup = now
        
        # Filter to requests within window
        self._memory_storage[key] = [
            ts for ts in self._memory_storage[key] 
            if ts > window_start
        ]
        
        current_count = len(self._memory_storage[key])
        remaining = max(0, limit - current_count - 1)
        reset_time = int(now + window)
        
        rate_info = {
            'limit': limit,
            'remaining': remaining,
            'reset': reset_time,
            'window': window
        }
        
        if current_count >= limit:
            return True, rate_info
        
        # Add current request
        self._memory_storage[key].append(now)
        
        return False, rate_info
    
    def _cleanup_memory(self):
        """Remove expired entries from memory storage"""
        now = time.time()
        max_window = max(self.TIME_UNITS.values())  # Longest possible window
        cutoff = now - max_window
        
        keys_to_delete = []
        for key, timestamps in self._memory_storage.items():
            self._memory_storage[key] = [ts for ts in timestamps if ts > cutoff]
            if not self._memory_storage[key]:
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del self._memory_storage[key]
        
        if keys_to_delete:
            logger.debug(f"Cleaned up {len(keys_to_delete)} expired rate limit keys")


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def init_rate_limiter(app: Sanic) -> RateLimiter:
    """Initialize global rate limiter with app"""
    global _rate_limiter
    _rate_limiter = RateLimiter(app)
    return _rate_limiter


def get_rate_limiter() -> Optional[RateLimiter]:
    """Get the global rate limiter instance"""
    return _rate_limiter


def rate_limit(
    rate: str,
    key_func: Optional[Callable[[Request], str]] = None,
    error_message: str = "Rate limit exceeded. Please try again later."
):
    """
    Decorator to apply rate limiting to a route
    
    Args:
        rate: Rate limit string (e.g., "5/minute", "100/hour")
        key_func: Optional function to generate custom key from request
        error_message: Message to return when rate limited
        
    Usage:
        @app.route('/api/login', methods=['POST'])
        @rate_limit("5/minute")
        async def login(request):
            ...
            
        @app.route('/api/expensive', methods=['GET'])
        @rate_limit("10/hour", key_func=lambda r: f"user:{r.ctx.user['user_id']}")
        async def expensive_operation(request):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            limiter = get_rate_limiter()
            
            if not limiter:
                # Rate limiter not initialized, allow request
                logger.warning("Rate limiter not initialized, skipping rate check")
                return await func(request, *args, **kwargs)
            
            # Generate rate limit key
            if key_func:
                key_suffix = key_func(request)
            else:
                key_suffix = limiter.get_client_ip(request)
            
            # Include endpoint in key to have separate limits per route
            endpoint = request.path
            key = f"{endpoint}:{key_suffix}"
            
            # Parse rate and check limit
            limit, window = limiter.parse_rate(rate)
            is_limited, rate_info = await limiter.is_rate_limited(key, limit, window)
            
            if is_limited:
                logger.warning(
                    f"Rate limit exceeded for {key}: "
                    f"{limit} requests per {window}s"
                )
                
                # Return 429 Too Many Requests
                return json({
                    'success': False,
                    'error': error_message,
                    'rate_limit': {
                        'limit': rate_info['limit'],
                        'remaining': 0,
                        'reset': rate_info['reset'],
                        'retry_after': rate_info['window']
                    }
                }, status=429, headers={
                    'X-RateLimit-Limit': str(rate_info['limit']),
                    'X-RateLimit-Remaining': '0',
                    'X-RateLimit-Reset': str(rate_info['reset']),
                    'Retry-After': str(rate_info['window'])
                })
            
            # Execute the actual route handler
            response = await func(request, *args, **kwargs)
            
            # Add rate limit headers to successful responses
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Limit'] = str(rate_info['limit'])
                response.headers['X-RateLimit-Remaining'] = str(rate_info['remaining'])
                response.headers['X-RateLimit-Reset'] = str(rate_info['reset'])
            
            return response
        
        return wrapper
    return decorator


# Predefined rate limits for common use cases
RATE_LIMITS = {
    'auth': "5/minute",          # Login/register - strict
    'api_write': "30/minute",    # POST/PUT/DELETE endpoints
    'api_read': "100/minute",    # GET endpoints
    'upload': "10/hour",         # File uploads
    'expensive': "5/hour",       # Expensive operations (reports, exports)
}
