"""
Production-grade observability for agentic assistant.
Structured JSON logging, OpenTelemetry tracing, and comprehensive metrics.
"""

import asyncio
import functools
import json
import logging
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
import threading


@dataclass
class TraceSpan:
    """OpenTelemetry-style span for operation tracking."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time: float
    end_time: Optional[float]
    duration_ms: Optional[float]
    status: str  # "started", "success", "error"
    attributes: Dict[str, Any]
    events: List[Dict[str, Any]]


@dataclass
class StructuredLogEntry:
    """Structured log entry for JSON logging."""
    timestamp: str
    level: str
    message: str
    trace_id: str
    session_id: str
    component: str
    operation: str
    phase: str
    duration_ms: Optional[float]
    outcome: str
    metadata: Dict[str, Any]


class StructuredLogger:
    """
    Production structured logger with trace correlation and JSON output.
    No emojis, no print statements - pure structured logging.
    """
    
    def __init__(self, name: str, log_file: Optional[Path] = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Configure JSON formatter
        if log_file:
            handler = logging.FileHandler(log_file)
        else:
            handler = logging.StreamHandler()
        
        handler.setFormatter(JSONFormatter())
        self.logger.addHandler(handler)
        
        # Thread-local storage for trace context
        self.local = threading.local()
    
    def set_trace_context(self, trace_id: str, session_id: str):
        """Set trace context for current thread."""
        self.local.trace_id = trace_id
        self.local.session_id = session_id
    
    def get_trace_context(self) -> tuple:
        """Get current trace context."""
        trace_id = getattr(self.local, 'trace_id', str(uuid.uuid4()))
        session_id = getattr(self.local, 'session_id', 'unknown')
        return trace_id, session_id
    
    def log_operation(self, 
                     component: str,
                     operation: str,
                     phase: str,
                     outcome: str,
                     duration_ms: Optional[float] = None,
                     **metadata):
        """Log structured operation with full context."""
        
        trace_id, session_id = self.get_trace_context()
        
        entry = StructuredLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level="INFO",
            message=f"{component}.{operation}.{phase}",
            trace_id=trace_id,
            session_id=session_id,
            component=component,
            operation=operation,
            phase=phase,
            duration_ms=duration_ms,
            outcome=outcome,
            metadata=metadata
        )
        
        self.logger.info(json.dumps(asdict(entry)))
    
    def log_error(self, component: str, operation: str, error: Exception, **metadata):
        """Log error with full context."""
        trace_id, session_id = self.get_trace_context()
        
        entry = StructuredLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level="ERROR",
            message=f"{component}.{operation}.error",
            trace_id=trace_id,
            session_id=session_id,
            component=component,
            operation=operation,
            phase="error",
            duration_ms=None,
            outcome="error",
            metadata={
                "error_type": type(error).__name__,
                "error_message": str(error),
                **metadata
            }
        )
        
        self.logger.error(json.dumps(asdict(entry)))
    
    def warning(self, message: str, **kwargs):
        """Log warning level message - compatibility method for standard logging."""
        trace_id, session_id = self.get_trace_context()
        
        # Create structured entry for warning
        entry = StructuredLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level="WARNING",
            message=message,
            trace_id=trace_id,
            session_id=session_id,
            component=kwargs.get('component', 'unknown'),
            operation=kwargs.get('operation', 'warning'),
            phase=kwargs.get('phase', 'log'),
            duration_ms=kwargs.get('duration_ms'),
            outcome=kwargs.get('outcome', 'logged'),
            metadata=kwargs
        )
        
        self.logger.warning(json.dumps(asdict(entry)))
    
    def info(self, message: str, **kwargs):
        """Log info level message - compatibility method for standard logging."""
        trace_id, session_id = self.get_trace_context()
        
        # Create structured entry for info
        entry = StructuredLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level="INFO",
            message=message,
            trace_id=trace_id,
            session_id=session_id,
            component=kwargs.get('component', 'unknown'),
            operation=kwargs.get('operation', 'info'),
            phase=kwargs.get('phase', 'log'),
            duration_ms=kwargs.get('duration_ms'),
            outcome=kwargs.get('outcome', 'logged'),
            metadata=kwargs
        )
        
        self.logger.info(json.dumps(asdict(entry)))
    
    def error(self, message: str, **kwargs):
        """Log error level message - compatibility method for standard logging."""
        trace_id, session_id = self.get_trace_context()
        
        # Create structured entry for error
        entry = StructuredLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level="ERROR",
            message=message,
            trace_id=trace_id,
            session_id=session_id,
            component=kwargs.get('component', 'unknown'),
            operation=kwargs.get('operation', 'error'),
            phase=kwargs.get('phase', 'log'),
            duration_ms=kwargs.get('duration_ms'),
            outcome=kwargs.get('outcome', 'error'),
            metadata=kwargs
        )
        
        self.logger.error(json.dumps(asdict(entry)))
    
    def debug(self, message: str, **kwargs):
        """Log debug level message - compatibility method for standard logging."""
        trace_id, session_id = self.get_trace_context()
        
        # Create structured entry for debug
        entry = StructuredLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level="DEBUG",
            message=message,
            trace_id=trace_id,
            session_id=session_id,
            component=kwargs.get('component', 'unknown'),
            operation=kwargs.get('operation', 'debug'),
            phase=kwargs.get('phase', 'log'),
            duration_ms=kwargs.get('duration_ms'),
            outcome=kwargs.get('outcome', 'logged'),
            metadata=kwargs
        )
        
        self.logger.debug(json.dumps(asdict(entry)))


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logs."""
    
    def format(self, record):
        # If already JSON, pass through
        if hasattr(record, 'getMessage') and record.getMessage().startswith('{'):
            return record.getMessage()
        
        # Otherwise, structure it
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)


class OperationTracer:
    """
    OpenTelemetry-style distributed tracing for operation visibility.
    """
    
    def __init__(self, logger: StructuredLogger):
        self.logger = logger
        self.active_spans: Dict[str, TraceSpan] = {}
        self.metrics_collector = MetricsCollector()
    
    @contextmanager
    def trace_operation(self, operation_name: str, **attributes):
        """Context manager for tracing operations with automatic timing."""
        
        trace_id, session_id = self.logger.get_trace_context()
        span_id = str(uuid.uuid4())[:8]
        
        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,  # Could enhance with parent tracking
            operation_name=operation_name,
            start_time=time.time(),
            end_time=None,
            duration_ms=None,
            status="started",
            attributes=attributes,
            events=[]
        )
        
        self.active_spans[span_id] = span
        
        # Log operation start (use component from attributes if provided, otherwise default to "tracer")
        component = attributes.pop("component", "tracer")
        self.logger.log_operation(
            component=component,
            operation=operation_name,
            phase="start",
            outcome="started",
            span_id=span_id,
            **attributes
        )
        
        try:
            yield span
            
            # Success
            span.status = "success"
            span.end_time = time.time()
            span.duration_ms = (span.end_time - span.start_time) * 1000
            
            # Use component from attributes if provided, otherwise default to "tracer"
            component = attributes.get("component", "tracer")
            self.logger.log_operation(
                component=component,
                operation=operation_name,
                phase="complete",
                outcome="success",
                duration_ms=span.duration_ms,
                span_id=span_id,
                **{k: v for k, v in attributes.items() if k != "component"}
            )
            
            # Collect metrics
            self.metrics_collector.record_operation(operation_name, span.duration_ms, "success")
            
        except Exception as e:
            # Error
            span.status = "error"
            span.end_time = time.time()
            span.duration_ms = (span.end_time - span.start_time) * 1000
            
            self.logger.log_error(
                component="tracer",
                operation=operation_name,
                error=e,
                span_id=span_id,
                duration_ms=span.duration_ms,
                **attributes
            )
            
            # Collect error metrics
            self.metrics_collector.record_operation(operation_name, span.duration_ms, "error")
            
            raise
        finally:
            # Clean up
            self.active_spans.pop(span_id, None)
    
    def add_event(self, span_id: str, event: str, **attributes):
        """Add event to active span."""
        if span_id in self.active_spans:
            self.active_spans[span_id].events.append({
                "timestamp": time.time(),
                "event": event,
                "attributes": attributes
            })


class MetricsCollector:
    """
    Metrics collection for monitoring and alerting.
    """
    
    def __init__(self):
        self.metrics: Dict[str, List[Dict[str, Any]]] = {
            "operation_counts": [],
            "operation_durations": [],
            "error_rates": [],
            "tool_usage": [],
            "llm_token_costs": []
        }
    
    def record_operation(self, operation: str, duration_ms: float, outcome: str):
        """Record operation metrics."""
        timestamp = time.time()
        
        self.metrics["operation_counts"].append({
            "timestamp": timestamp,
            "operation": operation,
            "outcome": outcome
        })
        
        self.metrics["operation_durations"].append({
            "timestamp": timestamp,
            "operation": operation,
            "duration_ms": duration_ms,
            "outcome": outcome
        })
    
    def record_tool_usage(self, tool_name: str, success: bool, response_time_ms: float):
        """Record tool usage metrics."""
        self.metrics["tool_usage"].append({
            "timestamp": time.time(),
            "tool": tool_name,
            "success": success,
            "response_time_ms": response_time_ms
        })
    
    def record_llm_usage(self, provider: str, model: str, input_tokens: int, output_tokens: int, cost_usd: float):
        """Record LLM usage and cost metrics."""
        self.metrics["llm_token_costs"].append({
            "timestamp": time.time(),
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": cost_usd
        })
    
    def get_metrics_summary(self, window_minutes: int = 60) -> Dict[str, Any]:
        """Get metrics summary for the last N minutes."""
        cutoff_time = time.time() - (window_minutes * 60)
        
        # Operation counts
        recent_ops = [m for m in self.metrics["operation_counts"] if m["timestamp"] > cutoff_time]
        op_summary = {}
        for op in recent_ops:
            key = f"{op['operation']}_{op['outcome']}"
            op_summary[key] = op_summary.get(key, 0) + 1
        
        # Average durations
        recent_durations = [m for m in self.metrics["operation_durations"] if m["timestamp"] > cutoff_time]
        duration_summary = {}
        for dur in recent_durations:
            op = dur["operation"]
            if op not in duration_summary:
                duration_summary[op] = []
            duration_summary[op].append(dur["duration_ms"])
        
        # Calculate averages
        for op in duration_summary:
            durations = duration_summary[op]
            duration_summary[op] = {
                "count": len(durations),
                "avg_ms": sum(durations) / len(durations),
                "min_ms": min(durations),
                "max_ms": max(durations)
            }
        
        # Tool usage
        recent_tools = [m for m in self.metrics["tool_usage"] if m["timestamp"] > cutoff_time]
        tool_summary = {}
        for tool in recent_tools:
            key = tool["tool"]
            if key not in tool_summary:
                tool_summary[key] = {"calls": 0, "successes": 0, "total_time_ms": 0}
            tool_summary[key]["calls"] += 1
            if tool["success"]:
                tool_summary[key]["successes"] += 1
            tool_summary[key]["total_time_ms"] += tool["response_time_ms"]
        
        # Calculate success rates
        for tool in tool_summary:
            summary = tool_summary[tool]
            summary["success_rate"] = summary["successes"] / summary["calls"]
            summary["avg_response_time_ms"] = summary["total_time_ms"] / summary["calls"]
        
        # LLM costs
        recent_llm = [m for m in self.metrics["llm_token_costs"] if m["timestamp"] > cutoff_time]
        total_cost = sum(m["cost_usd"] for m in recent_llm)
        total_tokens = sum(m["total_tokens"] for m in recent_llm)
        
        return {
            "window_minutes": window_minutes,
            "operations": op_summary,
            "durations": duration_summary,
            "tools": tool_summary,
            "llm_usage": {
                "total_calls": len(recent_llm),
                "total_cost_usd": total_cost,
                "total_tokens": total_tokens,
                "avg_cost_per_call": total_cost / len(recent_llm) if recent_llm else 0
            }
        }


# Global observability instances
logger = StructuredLogger("agentic_assistant", Path("logs/agent.log"))
tracer = OperationTracer(logger)


def get_observability():
    """Get global observability instances."""
    return logger, tracer


# Convenience decorators
def traced_operation(operation_name: str, **attributes):
    """Decorator for automatic operation tracing."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with tracer.trace_operation(operation_name, **attributes) as span:
                # Add function metadata
                span.attributes["function"] = func.__name__
                span.attributes["module"] = func.__module__
                return func(*args, **kwargs)
        return wrapper
    return decorator


def log_performance(component: str, operation: str):
    """Decorator for automatic performance logging."""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                logger.log_operation(
                    component=component,
                    operation=operation,
                    phase="complete",
                    outcome="success",
                    duration_ms=duration_ms,
                    function=func.__name__
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.log_error(
                    component=component,
                    operation=operation,
                    error=e,
                    duration_ms=duration_ms,
                    function=func.__name__
                )
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                logger.log_operation(
                    component=component,
                    operation=operation,
                    phase="complete",
                    outcome="success",
                    duration_ms=duration_ms,
                    function=func.__name__
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.log_error(
                    component=component,
                    operation=operation,
                    error=e,
                    duration_ms=duration_ms,
                    function=func.__name__
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator