"""
Structured observability system with OpenTelemetry tracing, metrics, and JSON logging.
Provides comprehensive monitoring for the RAG system.
"""

import json
import logging
import time
import traceback
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from enum import Enum

# OpenTelemetry imports with fallbacks
try:
    from opentelemetry import trace, metrics
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


class LogLevel(Enum):
    """Standard log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ComponentType(Enum):
    """System component types for organized logging."""
    RETRIEVAL = "retrieval"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    AGENT = "agent"
    API = "api"
    DATABASE = "database"
    STORAGE = "storage"
    SYSTEM = "system"


@dataclass
class LogEntry:
    """Structured log entry with comprehensive metadata."""
    timestamp: str
    level: str
    component: str
    operation: str
    message: str
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    user_id: Optional[str] = None
    duration_ms: Optional[float] = None
    status: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    business_metrics: Optional[Dict[str, Any]] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PerformanceMetrics:
    """Performance tracking for operations."""
    
    def __init__(self):
        self.start_time = time.time()
        self.checkpoints: Dict[str, float] = {}
        self.end_time: Optional[float] = None
    
    def checkpoint(self, name: str) -> None:
        """Add a timing checkpoint."""
        self.checkpoints[name] = time.time() - self.start_time
    
    def finish(self) -> Dict[str, float]:
        """Finish timing and return all metrics."""
        self.end_time = time.time()
        total_duration = self.end_time - self.start_time
        
        return {
            "total_duration_ms": total_duration * 1000,
            "checkpoints": {k: v * 1000 for k, v in self.checkpoints.items()}
        }


class StructuredLogger:
    """
    Structured JSON logger with OpenTelemetry integration.
    """
    
    def __init__(self, 
                 component: ComponentType,
                 log_file: Optional[Path] = None,
                 console_output: bool = True,
                 trace_enabled: bool = True):
        """
        Initialize structured logger.
        
        Args:
            component: Component type for this logger
            log_file: Optional file path for log output
            console_output: Whether to output to console
            trace_enabled: Whether to enable OpenTelemetry tracing
        """
        self.component = component.value
        self.trace_enabled = trace_enabled and OTEL_AVAILABLE
        
        # Setup standard logger
        self.logger = logging.getLogger(f"pio_ai.{self.component}")
        self.logger.setLevel(logging.INFO)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Add console handler if requested
        if console_output:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(self._create_formatter())
            self.logger.addHandler(console_handler)
        
        # Add file handler if requested
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(self._create_formatter())
            self.logger.addHandler(file_handler)
        
        # Initialize tracing if available
        if self.trace_enabled:
            self.tracer = trace.get_tracer(f"pio_ai.{self.component}")
        else:
            self.tracer = None
    
    def _create_formatter(self) -> logging.Formatter:
        """Create JSON formatter for structured logging."""
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                # Create base log entry
                log_data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": record.levelname,
                    "component": getattr(record, 'component', 'unknown'),
                    "operation": getattr(record, 'operation', 'unknown'),
                    "message": record.getMessage(),
                    "logger_name": record.name
                }
                
                # Add optional fields if present
                for field in ['session_id', 'turn_id', 'user_id', 'duration_ms', 
                             'status', 'error_details', 'performance_metrics',
                             'business_metrics', 'trace_id', 'span_id', 'metadata']:
                    if hasattr(record, field):
                        log_data[field] = getattr(record, field)
                
                # Add exception info if present
                if record.exc_info:
                    log_data['exception'] = {
                        'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                        'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                        'traceback': traceback.format_exception(*record.exc_info)
                    }
                
                return json.dumps(log_data, ensure_ascii=False)
        
        return JsonFormatter()
    
    def log(self, 
            level: LogLevel,
            operation: str,
            message: str,
            session_id: Optional[str] = None,
            turn_id: Optional[str] = None,
            user_id: Optional[str] = None,
            duration_ms: Optional[float] = None,
            status: Optional[str] = None,
            error_details: Optional[Dict[str, Any]] = None,
            performance_metrics: Optional[Dict[str, Any]] = None,
            business_metrics: Optional[Dict[str, Any]] = None,
            metadata: Optional[Dict[str, Any]] = None,
            exc_info: bool = False) -> None:
        """
        Log a structured message.
        """
        # Get current span context if tracing enabled
        trace_id = None
        span_id = None
        
        if self.trace_enabled and self.tracer:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                span_context = current_span.get_span_context()
                trace_id = format(span_context.trace_id, '032x')
                span_id = format(span_context.span_id, '016x')
        
        # Create log record with structured data
        extra = {
            'component': self.component,
            'operation': operation,
            'session_id': session_id,
            'turn_id': turn_id,
            'user_id': user_id,
            'duration_ms': duration_ms,
            'status': status,
            'error_details': error_details,
            'performance_metrics': performance_metrics,
            'business_metrics': business_metrics,
            'trace_id': trace_id,
            'span_id': span_id,
            'metadata': metadata
        }
        
        # Filter out None values
        extra = {k: v for k, v in extra.items() if v is not None}
        
        # Log with appropriate level
        log_level = getattr(logging, level.value)
        self.logger.log(log_level, message, extra=extra, exc_info=exc_info)
    
    def info(self, operation: str, message: str, **kwargs):
        """Log info level message."""
        self.log(LogLevel.INFO, operation, message, **kwargs)
    
    def warning(self, operation: str, message: str, **kwargs):
        """Log warning level message."""
        self.log(LogLevel.WARNING, operation, message, **kwargs)
    
    def error(self, operation: str, message: str, **kwargs):
        """Log error level message."""
        kwargs.setdefault('exc_info', True)
        self.log(LogLevel.ERROR, operation, message, **kwargs)
    
    def debug(self, operation: str, message: str, **kwargs):
        """Log debug level message."""
        self.log(LogLevel.DEBUG, operation, message, **kwargs)
    
    @contextmanager
    def trace_operation(self, 
                       operation_name: str,
                       session_id: Optional[str] = None,
                       turn_id: Optional[str] = None,
                       user_id: Optional[str] = None,
                       metadata: Optional[Dict[str, Any]] = None):
        """
        Context manager for tracing operations with performance metrics.
        """
        # Start performance tracking
        perf_metrics = PerformanceMetrics()
        span = None
        
        try:
            # Start OpenTelemetry span if available
            if self.trace_enabled and self.tracer:
                span = self.tracer.start_span(operation_name)
                span.set_attribute("component", self.component)
                if session_id:
                    span.set_attribute("session_id", session_id)
                if turn_id:
                    span.set_attribute("turn_id", turn_id)
                if user_id:
                    span.set_attribute("user_id", user_id)
                if metadata:
                    for key, value in metadata.items():
                        span.set_attribute(f"metadata.{key}", str(value))
            
            # Log operation start
            self.info(
                operation_name,
                f"Starting {operation_name}",
                session_id=session_id,
                turn_id=turn_id,
                user_id=user_id,
                status="started",
                metadata=metadata
            )
            
            yield perf_metrics
            
            # Operation completed successfully
            final_metrics = perf_metrics.finish()
            
            if span:
                span.set_status(Status(StatusCode.OK))
                span.set_attribute("duration_ms", final_metrics["total_duration_ms"])
            
            self.info(
                operation_name,
                f"Completed {operation_name}",
                session_id=session_id,
                turn_id=turn_id,
                user_id=user_id,
                duration_ms=final_metrics["total_duration_ms"],
                status="success",
                performance_metrics=final_metrics,
                metadata=metadata
            )
            
        except Exception as e:
            # Operation failed
            final_metrics = perf_metrics.finish()
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc()
            }
            
            if span:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.set_attribute("error", True)
                span.set_attribute("error_type", type(e).__name__)
            
            self.error(
                operation_name,
                f"Failed {operation_name}: {str(e)}",
                session_id=session_id,
                turn_id=turn_id,
                user_id=user_id,
                duration_ms=final_metrics["total_duration_ms"],
                status="error",
                error_details=error_details,
                performance_metrics=final_metrics,
                metadata=metadata
            )
            
            raise
            
        finally:
            if span:
                span.end()


class MetricsCollector:
    """
    Business and system metrics collection.
    """
    
    def __init__(self, metrics_file: Optional[Path] = None):
        """
        Initialize metrics collector.
        
        Args:
            metrics_file: Optional file for metrics storage
        """
        self.metrics_file = metrics_file
        self.metrics_data: List[Dict[str, Any]] = []
        
        # Initialize OpenTelemetry metrics if available
        if OTEL_AVAILABLE:
            try:
                self.meter = metrics.get_meter("pio_ai.metrics")
                
                # Create counters
                self.query_counter = self.meter.create_counter(
                    "queries_total",
                    description="Total number of queries processed"
                )
                
                self.error_counter = self.meter.create_counter(
                    "errors_total", 
                    description="Total number of errors"
                )
                
                # Create histograms
                self.query_duration_histogram = self.meter.create_histogram(
                    "query_duration_ms",
                    description="Query processing duration in milliseconds"
                )
                
                self.retrieval_relevance_histogram = self.meter.create_histogram(
                    "retrieval_relevance_score",
                    description="Retrieval relevance scores"
                )
                
            except Exception as e:
                logging.warning(f"Failed to initialize OpenTelemetry metrics: {e}")
                self.meter = None
        else:
            self.meter = None
    
    def record_query_metrics(self,
                           query_type: str,
                           duration_ms: float,
                           success: bool,
                           confidence_score: float,
                           tools_used: List[str],
                           session_id: Optional[str] = None) -> None:
        """Record metrics for a query."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Internal metrics storage
        metric_entry = {
            "timestamp": timestamp,
            "metric_type": "query",
            "query_type": query_type,
            "duration_ms": duration_ms,
            "success": success,
            "confidence_score": confidence_score,
            "tools_used": tools_used,
            "session_id": session_id
        }
        
        self.metrics_data.append(metric_entry)
        
        # OpenTelemetry metrics
        if self.meter:
            labels = {"query_type": query_type, "success": str(success)}
            
            self.query_counter.add(1, labels)
            self.query_duration_histogram.record(duration_ms, labels)
            
            if not success:
                self.error_counter.add(1, {"component": "query_processing"})
        
        # Save to file if configured
        if self.metrics_file:
            self._save_metrics()
    
    def record_retrieval_metrics(self,
                               retrieval_type: str,
                               results_count: int,
                               avg_relevance_score: float,
                               duration_ms: float) -> None:
        """Record metrics for retrieval operations."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        metric_entry = {
            "timestamp": timestamp,
            "metric_type": "retrieval",
            "retrieval_type": retrieval_type,
            "results_count": results_count,
            "avg_relevance_score": avg_relevance_score,
            "duration_ms": duration_ms
        }
        
        self.metrics_data.append(metric_entry)
        
        # OpenTelemetry metrics
        if self.meter:
            labels = {"retrieval_type": retrieval_type}
            self.retrieval_relevance_histogram.record(avg_relevance_score, labels)
        
        # Save to file if configured
        if self.metrics_file:
            self._save_metrics()
    
    def record_system_metrics(self,
                            component: str,
                            operation: str,
                            duration_ms: float,
                            memory_usage_mb: Optional[float] = None,
                            cpu_usage_percent: Optional[float] = None) -> None:
        """Record system performance metrics."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        metric_entry = {
            "timestamp": timestamp,
            "metric_type": "system",
            "component": component,
            "operation": operation,
            "duration_ms": duration_ms,
            "memory_usage_mb": memory_usage_mb,
            "cpu_usage_percent": cpu_usage_percent
        }
        
        self.metrics_data.append(metric_entry)
        
        # Save to file if configured
        if self.metrics_file:
            self._save_metrics()
    
    def _save_metrics(self) -> None:
        """Save metrics to file."""
        if not self.metrics_file:
            return
        
        try:
            # Keep only last 10000 metrics to prevent unbounded growth
            if len(self.metrics_data) > 10000:
                self.metrics_data = self.metrics_data[-10000:]
            
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.metrics_file, 'w') as f:
                json.dump(self.metrics_data, f, indent=2)
                
        except Exception as e:
            logging.warning(f"Failed to save metrics: {e}")
    
    def get_metrics_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get metrics summary for the last N hours."""
        cutoff_time = datetime.now(timezone.utc).timestamp() - (hours * 3600)
        
        recent_metrics = [
            m for m in self.metrics_data
            if datetime.fromisoformat(m["timestamp"].replace('Z', '+00:00')).timestamp() > cutoff_time
        ]
        
        if not recent_metrics:
            return {"message": "No recent metrics available"}
        
        # Calculate summaries
        query_metrics = [m for m in recent_metrics if m.get("metric_type") == "query"]
        retrieval_metrics = [m for m in recent_metrics if m.get("metric_type") == "retrieval"]
        
        summary = {
            "time_period_hours": hours,
            "total_queries": len(query_metrics),
            "successful_queries": len([m for m in query_metrics if m.get("success", False)]),
            "avg_query_duration_ms": sum(m.get("duration_ms", 0) for m in query_metrics) / max(len(query_metrics), 1),
            "avg_confidence_score": sum(m.get("confidence_score", 0) for m in query_metrics) / max(len(query_metrics), 1),
            "total_retrievals": len(retrieval_metrics),
            "avg_retrieval_relevance": sum(m.get("avg_relevance_score", 0) for m in retrieval_metrics) / max(len(retrieval_metrics), 1)
        }
        
        return summary


class ObservabilityManager:
    """
    Central manager for the complete observability system.
    """
    
    def __init__(self, 
                 base_path: Path = None,
                 enable_tracing: bool = True,
                 enable_metrics: bool = True,
                 jaeger_endpoint: Optional[str] = None):
        """
        Initialize observability manager.
        
        Args:
            base_path: Base path for logs and metrics storage
            enable_tracing: Whether to enable OpenTelemetry tracing
            enable_metrics: Whether to enable metrics collection
            jaeger_endpoint: Optional Jaeger endpoint for trace export
        """
        self.base_path = base_path or Path("data/observability")
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize OpenTelemetry if requested and available
        if enable_tracing and OTEL_AVAILABLE:
            self._setup_tracing(jaeger_endpoint)
        
        # Initialize metrics collector
        if enable_metrics:
            metrics_file = self.base_path / "metrics.json"
            self.metrics = MetricsCollector(metrics_file)
        else:
            self.metrics = None
        
        # Component loggers
        self.loggers: Dict[str, StructuredLogger] = {}
    
    def _setup_tracing(self, jaeger_endpoint: Optional[str] = None) -> None:
        """Setup OpenTelemetry tracing."""
        try:
            # Create resource
            resource = Resource.create({
                "service.name": "pio-ai-rag",
                "service.version": "1.0.0",
                "deployment.environment": "production"
            })
            
            # Setup tracer provider
            tracer_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(tracer_provider)
            
            # Add Jaeger exporter if endpoint provided
            if jaeger_endpoint:
                jaeger_exporter = JaegerExporter(
                    endpoint=jaeger_endpoint,
                    collector_endpoint=f"{jaeger_endpoint}/api/traces"
                )
                span_processor = BatchSpanProcessor(jaeger_exporter)
                tracer_provider.add_span_processor(span_processor)
            
            logging.info("OpenTelemetry tracing initialized")
            
        except Exception as e:
            logging.warning(f"Failed to setup tracing: {e}")
    
    def get_logger(self, component: ComponentType) -> StructuredLogger:
        """Get or create a structured logger for a component."""
        component_name = component.value
        
        if component_name not in self.loggers:
            log_file = self.base_path / "logs" / f"{component_name}.jsonl"
            self.loggers[component_name] = StructuredLogger(
                component=component,
                log_file=log_file,
                console_output=True,
                trace_enabled=OTEL_AVAILABLE
            )
        
        return self.loggers[component_name]
    
    def get_metrics_collector(self) -> Optional[MetricsCollector]:
        """Get the metrics collector."""
        return self.metrics
    
    def health_check(self) -> Dict[str, Any]:
        """Perform observability system health check."""
        health = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "healthy",
            "components": {
                "logging": "available",
                "metrics": "available" if self.metrics else "disabled",
                "tracing": "available" if OTEL_AVAILABLE else "unavailable",
                "storage": "available" if self.base_path.exists() else "unavailable"
            },
            "statistics": {}
        }
        
        # Add metrics summary if available
        if self.metrics:
            try:
                health["statistics"] = self.metrics.get_metrics_summary(hours=1)
            except Exception as e:
                health["components"]["metrics"] = f"error: {str(e)}"
        
        # Check if any component is failing
        failing_components = [
            comp for comp, status in health["components"].items()
            if status.startswith("error") or status == "unavailable"
        ]
        
        if failing_components:
            health["status"] = "degraded"
            health["issues"] = failing_components
        
        return health