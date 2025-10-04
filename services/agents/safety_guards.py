"""
Comprehensive safety guards for SQL validation, abuse detection, and compliance.
Implements Constitutional AI-style answer review.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass
from enum import Enum
import hashlib
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SafetyLevel(Enum):
    """Safety levels for operations."""
    SAFE = "safe"
    WARNING = "warning"
    BLOCKED = "blocked"


@dataclass
class SafetyResult:
    """Result of safety check."""
    safe: bool
    level: SafetyLevel
    reason: str
    violations: List[str]
    sanitized_content: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "safe": self.safe,
            "level": self.level.value,
            "reason": self.reason,
            "violations": self.violations,
            "sanitized_content": self.sanitized_content
        }


class SQLValidator:
    """
    Validate SQL queries for safety and compliance.
    Ensures only safe, read-only queries are executed.
    """
    
    # Forbidden SQL keywords that could modify data
    FORBIDDEN_KEYWORDS = {
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
        'TRUNCATE', 'REPLACE', 'MERGE', 'GRANT', 'REVOKE',
        'EXEC', 'EXECUTE', 'CALL', 'DO'
    }
    
    # Suspicious patterns that could indicate SQL injection
    SUSPICIOUS_PATTERNS = [
        r'--',  # SQL comments
        r'/\*.*\*/',  # Multi-line comments
        r';.*SELECT',  # Chained queries
        r'UNION\s+SELECT',  # Union-based injection
        r'OR\s+1\s*=\s*1',  # Always-true conditions
        r'OR\s+\'1\'\s*=\s*\'1\'',  # String-based always-true
        r'INFORMATION_SCHEMA',  # Schema introspection
        r'SYS\.',  # System tables
        r'xp_',  # Extended procedures (SQL Server)
        r'INTO\s+OUTFILE',  # File operations
        r'LOAD_FILE',  # File reading
    ]
    
    # Allowed SELECT patterns
    ALLOWED_PATTERNS = [
        r'^\s*SELECT',  # Must start with SELECT
        r'^\s*WITH\s+.+\s+SELECT',  # Common Table Expressions
        r'^\s*\(SELECT',  # Subqueries
    ]
    
    def __init__(self, max_query_length: int = 10000, max_tables: int = 10):
        """
        Initialize SQL validator.
        
        Args:
            max_query_length: Maximum allowed query length
            max_tables: Maximum number of tables in a query
        """
        self.max_query_length = max_query_length
        self.max_tables = max_tables
        self.compiled_suspicious = [re.compile(p, re.IGNORECASE) for p in self.SUSPICIOUS_PATTERNS]
        self.compiled_allowed = [re.compile(p, re.IGNORECASE) for p in self.ALLOWED_PATTERNS]
        
        logger.info("SQL validator initialized")
    
    def validate(self, sql: str) -> SafetyResult:
        """
        Validate SQL query for safety.
        
        Args:
            sql: SQL query to validate
            
        Returns:
            SafetyResult with validation details
        """
        violations = []
        
        # Check length
        if len(sql) > self.max_query_length:
            violations.append(f"Query exceeds maximum length ({self.max_query_length} chars)")
        
        # Check for forbidden keywords
        sql_upper = sql.upper()
        for keyword in self.FORBIDDEN_KEYWORDS:
            if re.search(rf'\b{keyword}\b', sql_upper):
                violations.append(f"Forbidden keyword detected: {keyword}")
        
        # Check for suspicious patterns
        for pattern in self.compiled_suspicious:
            if pattern.search(sql):
                violations.append(f"Suspicious pattern detected: {pattern.pattern}")
        
        # Check if it starts with SELECT (after whitespace)
        is_select = any(pattern.match(sql) for pattern in self.compiled_allowed)
        if not is_select:
            violations.append("Query must be a SELECT statement")
        
        # Check number of tables
        table_count = self._count_tables(sql)
        if table_count > self.max_tables:
            violations.append(f"Too many tables ({table_count} > {self.max_tables})")
        
        # Determine safety level
        if violations:
            logger.warning(
                f"SQL validation failed: {len(violations)} violations",
                extra={
                    "operation": "safety.sql_validation",
                    "violations": violations,
                    "sql": sql[:200]
                }
            )
            
            return SafetyResult(
                safe=False,
                level=SafetyLevel.BLOCKED,
                reason=f"SQL query violates {len(violations)} safety rule(s)",
                violations=violations
            )
        
        logger.info(
            "SQL query validated successfully",
            extra={
                "operation": "safety.sql_validation",
                "sql_length": len(sql),
                "table_count": table_count
            }
        )
        
        return SafetyResult(
            safe=True,
            level=SafetyLevel.SAFE,
            reason="Query passed all safety checks",
            violations=[]
        )
    
    def _count_tables(self, sql: str) -> int:
        """
        Count approximate number of tables in query.
        
        Args:
            sql: SQL query
            
        Returns:
            Estimated table count
        """
        # Simple heuristic: count FROM and JOIN clauses
        from_count = len(re.findall(r'\bFROM\b', sql, re.IGNORECASE))
        join_count = len(re.findall(r'\bJOIN\b', sql, re.IGNORECASE))
        return from_count + join_count


class AbuseDetector:
    """
    Detect abusive, offensive, or inappropriate queries.
    """
    
    # Offensive/abusive patterns
    ABUSE_PATTERNS = [
        r'\b(fuck|shit|damn|hell|bitch)\b',
        r'\b(idiot|stupid|dumb|moron)\b',
        r'\b(hate|kill|destroy)\b',
    ]
    
    # Off-topic patterns
    OFF_TOPIC_PATTERNS = [
        r'\b(weather|sports|politics|entertainment)\b',
        r'\b(recipe|cooking|game|movie)\b',
        r'tell me a (joke|story)',
        r'write (a poem|code|an essay)',
    ]
    
    POLITE_RESPONSES = [
        "I focus on database and data analysis tasks. How can I assist you with your AML system?",
        "I'm here to help with database queries and schema information. What would you like to know?",
        "Let's keep our discussion focused on the database. How can I help you access the data you need?",
        "I'm designed to assist with data queries. What information are you looking for?"
    ]
    
    def __init__(self):
        """Initialize abuse detector."""
        self.compiled_abuse = [re.compile(p, re.IGNORECASE) for p in self.ABUSE_PATTERNS]
        self.compiled_offtopic = [re.compile(p, re.IGNORECASE) for p in self.OFF_TOPIC_PATTERNS]
        
        # Rate limiting
        self.user_violations: Dict[str, List[datetime]] = {}
        self.violation_threshold = 3
        self.violation_window = timedelta(minutes=10)
        
        logger.info("Abuse detector initialized")
    
    def check(self, query: str, user_id: Optional[str] = None) -> SafetyResult:
        """
        Check query for abuse or off-topic content.
        
        Args:
            query: User query
            user_id: Optional user identifier for rate limiting
            
        Returns:
            SafetyResult
        """
        violations = []
        
        # Check for abusive content
        for pattern in self.compiled_abuse:
            if pattern.search(query):
                violations.append(f"Inappropriate language detected")
                break
        
        # Check for off-topic content
        for pattern in self.compiled_offtopic:
            if pattern.search(query):
                violations.append(f"Off-topic request detected")
                break
        
        # Check rate limiting if user_id provided
        if user_id and violations:
            if self._is_rate_limited(user_id):
                violations.append("Rate limit exceeded")
                
                logger.warning(
                    f"User rate limited: {user_id}",
                    extra={
                        "operation": "safety.rate_limit",
                        "user_id": user_id,
                        "violations": len(self.user_violations.get(user_id, []))
                    }
                )
        
        if violations:
            logger.info(
                f"Abuse detected: {violations}",
                extra={
                    "operation": "safety.abuse_detection",
                    "query": query[:100],
                    "violations": violations
                }
            )
            
            return SafetyResult(
                safe=False,
                level=SafetyLevel.BLOCKED,
                reason="Query violates usage policy",
                violations=violations
            )
        
        return SafetyResult(
            safe=True,
            level=SafetyLevel.SAFE,
            reason="Query is appropriate",
            violations=[]
        )
    
    def _is_rate_limited(self, user_id: str) -> bool:
        """
        Check if user is rate limited.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if rate limited
        """
        now = datetime.now()
        
        # Initialize user violations list
        if user_id not in self.user_violations:
            self.user_violations[user_id] = []
        
        # Clean old violations
        self.user_violations[user_id] = [
            v for v in self.user_violations[user_id]
            if now - v < self.violation_window
        ]
        
        # Add current violation
        self.user_violations[user_id].append(now)
        
        # Check threshold
        return len(self.user_violations[user_id]) > self.violation_threshold
    
    def get_polite_response(self) -> str:
        """Get a random polite response."""
        import random
        return random.choice(self.POLITE_RESPONSES)


class ConstitutionalAnswerReviewer:
    """
    Review generated answers for compliance and safety.
    Inspired by Constitutional AI principles.
    """
    
    # Compliance rules
    RULES = {
        "no_pii": {
            "description": "Do not reveal personally identifiable information",
            "patterns": [
                r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
                r'\b\d{16}\b',  # Credit card
                r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',  # Email
            ],
            "severity": "high"
        },
        "no_credentials": {
            "description": "Do not reveal passwords or credentials",
            "patterns": [
                r'\bpassword\s*[:=]\s*\S+',
                r'\bapi[_-]?key\s*[:=]\s*\S+',
                r'\btoken\s*[:=]\s*\S+',
            ],
            "severity": "critical"
        },
        "no_harmful_instructions": {
            "description": "Do not provide harmful or illegal instructions",
            "patterns": [
                r'\bhow to (hack|crack|break into)',
                r'\bevade (detection|monitoring|compliance)',
            ],
            "severity": "critical"
        },
        "no_confidential_disclosure": {
            "description": "Do not disclose confidential business information",
            "patterns": [
                r'\bconfidential\b.*\bresults\b',
                r'\binternal only\b',
            ],
            "severity": "high"
        }
    }
    
    def __init__(self, llm_client: Optional[Any] = None):
        """
        Initialize constitutional reviewer.
        
        Args:
            llm_client: Optional LLM for advanced review
        """
        self.llm_client = llm_client
        self.compiled_rules = {}
        
        # Compile patterns
        for rule_id, rule in self.RULES.items():
            self.compiled_rules[rule_id] = {
                'description': rule['description'],
                'patterns': [re.compile(p, re.IGNORECASE) for p in rule['patterns']],
                'severity': rule['severity']
            }
        
        logger.info("Constitutional answer reviewer initialized")
    
    def review(self, answer: str, query_context: Optional[Dict[str, Any]] = None) -> SafetyResult:
        """
        Review generated answer for compliance.
        
        Args:
            answer: Generated answer text
            query_context: Optional context about the query
            
        Returns:
            SafetyResult with review details
        """
        violations = []
        severity_levels = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
        max_severity = 0
        
        # Check each rule
        for rule_id, rule_data in self.compiled_rules.items():
            for pattern in rule_data['patterns']:
                if pattern.search(answer):
                    violation_msg = f"{rule_data['description']} (rule: {rule_id})"
                    violations.append(violation_msg)
                    
                    severity = severity_levels.get(rule_data['severity'], 0)
                    max_severity = max(max_severity, severity)
                    
                    logger.warning(
                        f"Constitutional violation: {rule_id}",
                        extra={
                            "operation": "safety.constitutional_review",
                            "rule_id": rule_id,
                            "severity": rule_data['severity'],
                            "answer_preview": answer[:100]
                        }
                    )
        
        # Determine action based on severity
        if max_severity >= 4:  # Critical
            return SafetyResult(
                safe=False,
                level=SafetyLevel.BLOCKED,
                reason="Answer contains critical policy violations",
                violations=violations,
                sanitized_content=self._generate_safe_fallback()
            )
        elif max_severity >= 3:  # High
            # Try to sanitize
            sanitized = self._sanitize_answer(answer, violations)
            return SafetyResult(
                safe=False,
                level=SafetyLevel.WARNING,
                reason="Answer contains policy violations but was sanitized",
                violations=violations,
                sanitized_content=sanitized
            )
        elif violations:
            # Low/medium violations - warn but allow
            return SafetyResult(
                safe=True,
                level=SafetyLevel.WARNING,
                reason="Minor policy concerns detected",
                violations=violations
            )
        
        # All clear
        return SafetyResult(
            safe=True,
            level=SafetyLevel.SAFE,
            reason="Answer passes constitutional review",
            violations=[]
        )
    
    def _sanitize_answer(self, answer: str, violations: List[str]) -> str:
        """
        Attempt to sanitize answer by removing violations.
        
        Args:
            answer: Original answer
            violations: List of violations
            
        Returns:
            Sanitized answer
        """
        sanitized = answer
        
        # Remove email addresses
        sanitized = re.sub(
            r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',
            '[EMAIL REDACTED]',
            sanitized,
            flags=re.IGNORECASE
        )
        
        # Remove SSN-like patterns
        sanitized = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN REDACTED]', sanitized)
        
        # Remove credential patterns
        sanitized = re.sub(
            r'(password|api[_-]?key|token)\s*[:=]\s*\S+',
            r'\1: [REDACTED]',
            sanitized,
            flags=re.IGNORECASE
        )
        
        return sanitized
    
    def _generate_safe_fallback(self) -> str:
        """Generate a safe fallback response."""
        return (
            "I apologize, but I cannot provide that information due to policy constraints. "
            "Please rephrase your question or ask about something else."
        )


class ComprehensiveSafetyGuards:
    """
    Main safety guard system integrating all validators.
    """
    
    def __init__(
        self,
        sql_validator: Optional[SQLValidator] = None,
        abuse_detector: Optional[AbuseDetector] = None,
        answer_reviewer: Optional[ConstitutionalAnswerReviewer] = None
    ):
        """
        Initialize comprehensive safety guards.
        
        Args:
            sql_validator: SQL validation system
            abuse_detector: Abuse detection system
            answer_reviewer: Answer review system
        """
        self.sql_validator = sql_validator or SQLValidator()
        self.abuse_detector = abuse_detector or AbuseDetector()
        self.answer_reviewer = answer_reviewer or ConstitutionalAnswerReviewer()
        
        logger.info(
            "Comprehensive safety guards initialized",
            extra={"operation": "safety.init"}
        )
    
    def check_query(self, query: str, user_id: Optional[str] = None) -> SafetyResult:
        """
        Check user query for safety.
        
        Args:
            query: User query
            user_id: Optional user identifier
            
        Returns:
            SafetyResult
        """
        return self.abuse_detector.check(query, user_id)
    
    def validate_sql(self, sql: str) -> SafetyResult:
        """
        Validate SQL for safety.
        
        Args:
            sql: SQL query
            
        Returns:
            SafetyResult
        """
        return self.sql_validator.validate(sql)
    
    def review_answer(
        self,
        answer: str,
        query_context: Optional[Dict[str, Any]] = None
    ) -> SafetyResult:
        """
        Review generated answer.
        
        Args:
            answer: Generated answer
            query_context: Query context
            
        Returns:
            SafetyResult
        """
        return self.answer_reviewer.review(answer, query_context)
    
    def full_check(
        self,
        query: str,
        sql: Optional[str] = None,
        answer: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, SafetyResult]:
        """
        Perform full safety check on all components.
        
        Args:
            query: User query
            sql: Generated SQL (optional)
            answer: Generated answer (optional)
            user_id: User identifier (optional)
            
        Returns:
            Dictionary of safety results
        """
        results = {}
        
        # Check query
        results['query'] = self.check_query(query, user_id)
        
        # Check SQL if provided
        if sql:
            results['sql'] = self.validate_sql(sql)
        
        # Check answer if provided
        if answer:
            results['answer'] = self.review_answer(answer)
        
        # Overall safety
        all_safe = all(r.safe for r in results.values())
        
        logger.info(
            f"Full safety check complete: {'PASSED' if all_safe else 'FAILED'}",
            extra={
                "operation": "safety.full_check",
                "all_safe": all_safe,
                "checks_performed": list(results.keys())
            }
        )
        
        return results
