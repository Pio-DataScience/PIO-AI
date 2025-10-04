"""
Enhanced observability system with structured logging, trace IDs, and performance metrics.
Implements comprehensive monitoring for production deployment.
"""

import logging
import json
import sys
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
import uuid
from contextlib import contextmanager
import time

# Configure structured JSON logging
class StructuredFormatter(logging.Formatter):
    """Custom JSON formatter for structured logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add extra fields
        if hasattr(record, 'trace_id'):
            log_data['trace_id'] = record.trace_id
        if hasattr(record, 'session_id'):
            log_data['session_id'] = record.session_id
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'operation'):
            log_data['operation'] = record.operation
        
        # Add any other extra fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'msecs',
                          'message', 'pathname', 'process', 'processName',
                          'relativeCreated', 'thread', 'threadName', 'exc_info',
                          'exc_text', 'stack_info', 'trace_id', 'session_id',
                          'user_id', 'operation']:
                log_data[key] = value
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }
        
        return json.dumps(log_data)


@dataclass
class PerformanceMetrics:
    """Performance metrics for an operation."""
    operation: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def complete(self, success: bool = True, error: Optional[str] = None):
        """Mark operation as complete."""
        self.end_time = datetime.now()
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.success = success
        self.error = error
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['start_time'] = self.start_time.isoformat()
        if self.end_time:
            data['end_time'] = self.end_time.isoformat()
        return data


class TraceContext:
    """Context for distributed tracing."""
    
    def __init__(
        self,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """
        Initialize trace context.
        
        Args:
            trace_id: Unique trace identifier
            session_id: Session identifier
            user_id: User identifier
        """
        self.trace_id = trace_id or str(uuid.uuid4())
        self.session_id = session_id
        self.user_id = user_id
        self.spans: List[PerformanceMetrics] = []
        self.start_time = datetime.now()
    
    def create_span(self, operation: str, metadata: Optional[Dict[str, Any]] = None) -> PerformanceMetrics:
        """
        Create a new span for an operation.
        
        Args:
            operation: Name of operation
            metadata: Additional metadata
            
        Returns:
            PerformanceMetrics span
        """
        span = PerformanceMetrics(
            operation=operation,
            start_time=datetime.now(),
            metadata=metadata or {}
        )
        self.spans.append(span)
        return span
    
    def get_summary(self) -> Dict[str, Any]:
        """Get trace summary."""
        total_duration = (datetime.now() - self.start_time).total_seconds() * 1000
        
        return {
            'trace_id': self.trace_id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'total_duration_ms': total_duration,
            'span_count': len(self.spans),
            'failed_spans': sum(1 for s in self.spans if not s.success),
            'spans': [s.to_dict() for s in self.spans]
        }


class EnhancedObservability:
    """
    Enhanced observability system with structured logging and metrics.
    """
    
    def __init__(
        self,
        log_level: str = "INFO",
        log_file: Optional[Path] = None,
        enable_console: bool = True,
        enable_json: bool = True
    ):
        """
        Initialize observability system.
        
        Args:
            log_level: Logging level
            log_file: Optional log file path
            enable_console: Enable console logging
            enable_json: Enable JSON structured logging
        """
        self.log_level = log_level
        self.log_file = log_file
        self.enable_console = enable_console
        self.enable_json = enable_json
        
        # Active traces
        self.active_traces: Dict[str, TraceContext] = {}
        
        # Metrics aggregation
        self.operation_metrics: Dict[str, List[float]] = {}
        self.error_counts: Dict[str, int] = {}
        
        # Configure logging
        self._configure_logging()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(
            "Observability system initialized",
            extra={
                "operation": "observability.init",
                "log_level": log_level,
                "json_enabled": enable_json
            }
        )
    
    def _configure_logging(self):
        """Configure logging handlers and formatters."""
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # Remove existing handlers
        root_logger.handlers = []
        
        # Console handler
        if self.enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            
            if self.enable_json:
                console_handler.setFormatter(StructuredFormatter())
            else:
                console_handler.setFormatter(
                    logging.Formatter(
                        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                    )
                )
            
            root_logger.addHandler(console_handler)
        
        # File handler
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(self.log_file)
            
            if self.enable_json:
                file_handler.setFormatter(StructuredFormatter())
            else:
                file_handler.setFormatter(
                    logging.Formatter(
                        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                    )
                )
            
            root_logger.addHandler(file_handler)
    
    def start_trace(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> TraceContext:
        """
        Start a new trace.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            trace_id: Optional trace ID (generated if not provided)
            
        Returns:
            TraceContext
        """
        trace = TraceContext(
            trace_id=trace_id,
            session_id=session_id,
            user_id=user_id
        )
        
        self.active_traces[trace.trace_id] = trace
        
        self.logger.info(
            f"Trace started: {trace.trace_id}",
            extra={
                "operation": "trace.start",
                "trace_id": trace.trace_id,
                "session_id": session_id,
                "user_id": user_id
            }
        )
        
        return trace
    
    def end_trace(self, trace_id: str) -> Dict[str, Any]:
        """
        End a trace and return summary.
        
        Args:
            trace_id: Trace identifier
            
        Returns:
            Trace summary
        """
        trace = self.active_traces.get(trace_id)
        
        if not trace:
            self.logger.warning(f"Trace not found: {trace_id}")
            return {}
        
        summary = trace.get_summary()
        
        self.logger.info(
            f"Trace completed: {trace_id}",
            extra={
                "operation": "trace.end",
                "trace_id": trace_id,
                "duration_ms": summary['total_duration_ms'],
                "span_count": summary['span_count'],
                "failed_spans": summary['failed_spans']
            }
        )
        
        # Aggregate metrics
        for span_data in summary['spans']:
            operation = span_data['operation']
            if span_data['duration_ms']:
                if operation not in self.operation_metrics:
                    self.operation_metrics[operation] = []
                self.operation_metrics[operation].append(span_data['duration_ms'])
            
            if not span_data['success']:
                self.error_counts[operation] = self.error_counts.get(operation, 0) + 1
        
        # Remove from active
        del self.active_traces[trace_id]
        
        return summary
    
    @contextmanager
    def trace_operation(
        self,
        operation: str,
        trace_context: Optional[TraceContext] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Context manager for tracing an operation.
        
        Args:
            operation: Operation name
            trace_context: Optional trace context
            metadata: Additional metadata
            
        Yields:
            PerformanceMetrics span
        """
        # Create or use trace
        if trace_context is None:
            trace_context = self.start_trace()
            auto_created = True
        else:
            auto_created = False
        
        # Create span
        span = trace_context.create_span(operation, metadata)
        
        self.logger.debug(
            f"Operation started: {operation}",
            extra={
                "operation": operation,
                "trace_id": trace_context.trace_id,
                "session_id": trace_context.session_id
            }
        )
        
        try:
            yield span
            span.complete(success=True)
            
            self.logger.info(
                f"Operation completed: {operation}",
                extra={
                    "operation": operation,
                    "trace_id": trace_context.trace_id,
                    "duration_ms": span.duration_ms,
                    "success": True
                }
            )
            
        except Exception as e:
            span.complete(success=False, error=str(e))
            
            self.logger.error(
                f"Operation failed: {operation}",
                extra={
                    "operation": operation,
                    "trace_id": trace_context.trace_id,
                    "duration_ms": span.duration_ms,
                    "error": str(e),
                    "success": False
                },
                exc_info=True
            )
            
            raise
        
        finally:
            if auto_created:
                self.end_trace(trace_context.trace_id)
    
    def log_event(
        self,
        event_type: str,
        message: str,
        level: str = "INFO",
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **extra_fields
    ):
        """
        Log a structured event.
        
        Args:
            event_type: Type of event
            message: Event message
            level: Log level
            trace_id: Optional trace ID
            session_id: Optional session ID
            user_id: Optional user ID
            **extra_fields: Additional fields
        """
        extra = {
            "event_type": event_type,
            "trace_id": trace_id,
            "session_id": session_id,
            "user_id": user_id,
            **extra_fields
        }
        
        log_func = getattr(self.logger, level.lower(), self.logger.info)
        log_func(message, extra=extra)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get aggregated metrics summary.
        
        Returns:
            Metrics summary
        """
        summary = {
            "operations": {},
            "total_errors": sum(self.error_counts.values()),
            "error_by_operation": self.error_counts.copy()
        }
        
        for operation, durations in self.operation_metrics.items():
            if durations:
                summary["operations"][operation] = {
                    "count": len(durations),
                    "avg_ms": sum(durations) / len(durations),
                    "min_ms": min(durations),
                    "max_ms": max(durations),
                    "p50_ms": self._percentile(durations, 50),
                    "p95_ms": self._percentile(durations, 95),
                    "p99_ms": self._percentile(durations, 99)
                }
        
        return summary
    
    @staticmethod
    def _percentile(values: List[float], percentile: int) -> float:
        """Calculate percentile."""
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    def export_metrics(self, output_path: Path):
        """
        Export metrics to JSON file.
        
        Args:
            output_path: Output file path
        """
        summary = self.get_metrics_summary()
        summary['exported_at'] = datetime.now().isoformat()
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dumps(summary, f, indent=2)
        
        self.logger.info(
            f"Metrics exported to {output_path}",
            extra={"operation": "metrics.export", "path": str(output_path)}
        )


# Global observability instance
_global_observability: Optional[EnhancedObservability] = None


def get_observability() -> EnhancedObservability:
    """Get global observability instance."""
    global _global_observability
    
    if _global_observability is None:
        _global_observability = EnhancedObservability(
            log_level="INFO",
            log_file=Path("logs/agent.log"),
            enable_console=True,
            enable_json=True
        )
    
    return _global_observability


def configure_observability(
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    enable_console: bool = True,
    enable_json: bool = True
) -> EnhancedObservability:
    """
    Configure global observability.
    
    Args:
        log_level: Logging level
        log_file: Optional log file path
        enable_console: Enable console logging
        enable_json: Enable JSON structured logging
        
    Returns:
        Configured EnhancedObservability instance
    """
    global _global_observability
    
    _global_observability = EnhancedObservability(
        log_level=log_level,
        log_file=log_file,
        enable_console=enable_console,
        enable_json=enable_json
    )
    
    return _global_observability


# Convenience decorators
def traced_operation(operation_name: str):
    """Decorator for tracing functions."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            obs = get_observability()
            with obs.trace_operation(operation_name):
                return func(*args, **kwargs)
        return wrapper
    return decorator
