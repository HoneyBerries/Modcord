"""
Performance monitoring for database operations.

Tracks query execution times, generates statistics, and logs slow queries
to help identify performance bottlenecks.
"""

from typing import Dict
from modcord.util.logger import get_logger

logger = get_logger("database_perf_mon")


class DatabasePerformanceMonitor:
    """
    Monitors and tracks database query performance.
    
    Records execution times for each query type and provides
    statistics including average, min, max times, and query counts.
    """
    
    def __init__(self, slow_query_threshold_ms: float = 100.0):
        """
        Initialize the performance monitor.
        
        Args:
            slow_query_threshold_ms: Threshold in milliseconds for logging slow queries
        """
        self._query_stats: Dict[str, Dict[str, float]] = {}
        self._slow_query_threshold = slow_query_threshold_ms / 1000.0  # Convert to seconds
    
    def track(self, query_name: str, duration: float) -> None:
        """
        Track a query execution.
        
        Args:
            query_name: Name/identifier of the query
            duration: Execution time in seconds
        """
        if query_name not in self._query_stats:
            self._query_stats[query_name] = {
                'count': 0,
                'total_time': 0.0,
                'min_time': float('inf'),
                'max_time': 0.0
            }
        
        stats = self._query_stats[query_name]
        stats['count'] += 1
        stats['total_time'] += duration
        stats['min_time'] = min(stats['min_time'], duration)
        stats['max_time'] = max(stats['max_time'], duration)
        
        # Log slow queries
        if duration > self._slow_query_threshold:
            logger.warning(
                "[PERFORMANCE] Slow query: %s took %.2fms",
                query_name, duration * 1000
            )
    
    def get_statistics(self) -> Dict[str, Dict[str, float]]:
        """
        Get query performance statistics.
        
        Returns:
            Dictionary mapping query names to their statistics
        """
        result = {}
        for query_name, stats in self._query_stats.items():
            result[query_name] = {
                'count': stats['count'],
                'total_time': stats['total_time'],
                'avg_time': stats['total_time'] / stats['count'] if stats['count'] > 0 else 0,
                'min_time': stats['min_time'] if stats['min_time'] != float('inf') else 0,
                'max_time': stats['max_time']
            }
        return result
    
    def reset(self) -> None:
        """Reset all performance statistics."""
        self._query_stats.clear()
        logger.info("[PERFORMANCE] Statistics reset")
    
    def get_summary(self) -> str:
        """
        Get a human-readable summary of performance statistics.
        
        Returns:
            Formatted string with performance summary
        """
        stats = self.get_statistics()
        if not stats:
            return "No queries tracked yet"
        
        lines = ["Database Performance Summary:", "=" * 50]
        for query_name, query_stats in sorted(stats.items()):
            lines.append(
                f"{query_name}:\n"
                f"  Count: {query_stats['count']}\n"
                f"  Avg: {query_stats['avg_time']*1000:.2f}ms\n"
                f"  Min: {query_stats['min_time']*1000:.2f}ms\n"
                f"  Max: {query_stats['max_time']*1000:.2f}ms\n"
                f"  Total: {query_stats['total_time']:.2f}s"
            )
        return "\n".join(lines)
