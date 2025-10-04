"""
Modern Agentic Chat Router - LLM-first, tool-aware conversation and intent classification.
Follows industry standards for natural conversation with dynamic tool invocation.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """Standard intent categories for agentic assistants."""
    CONVERSATION = "conversation"  # Small-talk, identity, capabilities
    SCHEMA = "schema"             # Table/column structure queries
    DATA_ANALYSIS = "data_analysis"  # Data exploration, counts, analysis
    FOLLOW_UP = "follow_up"       # Contextual continuation
    GENERAL = "general"           # Mixed/unclear intent
    ABUSE = "abuse"              # Harassment, toxicity


@dataclass
class IntentClassification:
    """Rich intent classification with entities and confidence."""
    intent: IntentType
    confidence: float
    entities: Dict[str, List[str]]
    requires_tools: bool
    context_carryover: List[str]
    reasoning: str


@dataclass
class ConversationTurn:
    """Structured turn with full context."""
    turn_id: str
    query: str
    intent: IntentType
    entities: Dict[str, List[str]]
    tools_used: List[str]
    response: str
    confidence: float
    timestamp: datetime
    context_inherited: Dict[str, Any]


class ModernAgenticRouter:
    """
    LLM-first router that understands conversation naturally and routes to tools when needed.
    """
    
    def __init__(self, llm_provider):
        self.llm_provider = llm_provider
        
        # Known business entities for extraction
        self.schema_entities = ["table", "column", "schema", "index", "constraint"]
        self.business_entities = ["customer", "account", "transaction", "aml", "risk", "compliance"]
        self.db_entities = ["oracle", "sql", "query", "database", "pio_", "bi_dwh"]
        
        # Abuse detection patterns
        self.abuse_patterns = [
            "stupid", "idiot", "useless", "shut up", "fuck", "shit", 
            "hate you", "kill", "die", "worse", "terrible"
        ]
    
    def classify_intent(self, query: str, session_context: Dict[str, Any]) -> IntentClassification:
        """
        LLM-aided intent classification with entity extraction and context carryover.
        """
        logger.warning(f"ROUTER DEBUG: Starting intent classification for query: '{query}'")
        logger.warning(f"ROUTER DEBUG: Session context: {session_context}")
        logger.warning(f"ROUTER DEBUG: LLM provider available: {self.llm_provider is not None}")
        
        try:
            # Quick pattern-based pre-filtering for efficiency
            logger.warning(f"ROUTER DEBUG: Attempting quick classification first")
            quick_classification = self._quick_classify(query, session_context)
            logger.warning(f"ROUTER DEBUG: Quick classification result: intent={quick_classification.intent.value}, confidence={quick_classification.confidence}")
            
            if quick_classification.confidence > 0.9:
                logger.warning(f"ROUTER DEBUG: Using quick classification (confidence > 0.9)")
                return quick_classification
            
            # Use LLM for nuanced classification
            logger.warning(f"ROUTER DEBUG: Quick classification confidence too low, trying LLM classification")
            llm_result = self._llm_classify(query, session_context)
            logger.warning(f"ROUTER DEBUG: LLM classification result: intent={llm_result.intent.value}, confidence={llm_result.confidence}")
            return llm_result
            
        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            # Safe fallback
            return IntentClassification(
                intent=IntentType.GENERAL,
                confidence=0.3,
                entities={},
                requires_tools=True,
                context_carryover=[],
                reasoning="Classification failed, defaulting to general"
            )
    
    def _quick_classify(self, query: str, session_context: Dict[str, Any]) -> IntentClassification:
        """Fast pattern-based classification for obvious cases."""
        query_lower = query.lower().strip()
        
        # Abuse detection
        if any(pattern in query_lower for pattern in self.abuse_patterns):
            return IntentClassification(
                intent=IntentType.ABUSE,
                confidence=0.95,
                entities={},
                requires_tools=False,
                context_carryover=[],
                reasoning="Detected abusive language"
            )
        
        # Simple greetings
        greetings = ["hi", "hello", "hey", "good morning", "good evening"]
        if query_lower in greetings or any(f"{g} " in query_lower for g in greetings):
            return IntentClassification(
                intent=IntentType.CONVERSATION,
                confidence=0.95,
                entities={},
                requires_tools=False,
                context_carryover=[],
                reasoning="Simple greeting detected"
            )
        
        # Identity questions
        identity_questions = ["who are you", "what are you", "what can you do"]
        if any(q in query_lower for q in identity_questions):
            return IntentClassification(
                intent=IntentType.CONVERSATION,
                confidence=0.95,
                entities={},
                requires_tools=False,
                context_carryover=[],
                reasoning="Identity question detected"
            )
        
        # Follow-up indicators with recent context
        recent_entities = session_context.get("recent_entities", {})
        turn_count = session_context.get("turn_count", 0)
        
        follow_up_words = ["which", "what about", "how many", "show me", "those", "them", "it", "more", "also", "and", "too", "further", "additional"]
        continuation_phrases = ["tell me more", "more about", "more details", "more specific", "give me more", "what else", "now tell me", "great, now", "ok, now"]
        
        # Check for explicit continuation phrases first
        has_continuation = any(phrase in query_lower for phrase in continuation_phrases)
        has_follow_up_words = any(word in query_lower for word in follow_up_words)
        
        print(f'QUICK_CLASSIFY: has_continuation={has_continuation}, has_follow_up_words={has_follow_up_words}, turn_count={turn_count}')
        
        if turn_count > 0 and (has_continuation or (recent_entities and has_follow_up_words)):
            return IntentClassification(
                intent=IntentType.FOLLOW_UP,
                confidence=0.85,
                entities=recent_entities,
                requires_tools=True,
                context_carryover=list(recent_entities.keys()),
                reasoning=f"Follow-up detected: continuation={has_continuation}, context_words={has_follow_up_words}, turn_count={turn_count}"
            )
        
        # Default to LLM classification for complex cases
        return IntentClassification(
            intent=IntentType.GENERAL,
            confidence=0.3,
            entities={},
            requires_tools=True,
            context_carryover=[],
            reasoning="Requires LLM analysis"
        )
    
    def _llm_classify(self, query: str, session_context: Dict[str, Any]) -> IntentClassification:
        """LLM-powered classification for nuanced understanding."""
        
        logger.warning(f"LLM DEBUG: Starting LLM classification")
        
        # Build rich context-aware prompt with conversation history
        recent_turns = session_context.get("recent_turns", [])
        recent_entities = session_context.get("recent_entities", {})
        recent_tables = session_context.get("recent_tables", [])
        last_answer_summary = session_context.get("last_answer_summary", "")
        episodic_summary = session_context.get("episodic_summary", "")
        
        # Build structured conversation context
        context_parts = []
        
        if episodic_summary:
            context_parts.append(f"Session Summary: {episodic_summary}")
        
        if recent_tables:
            context_parts.append(f"Recently Discussed Tables: {', '.join(recent_tables[-3:])}")
        
        if last_answer_summary:
            context_parts.append(f"System's Last Response: {last_answer_summary}")
        
        if recent_turns:
            context_parts.append(f"Last 2 User Queries: {' | '.join(recent_turns[-2:])}")
        
        if recent_entities:
            entities_str = ", ".join([f"{k}: {v}" for k, v in recent_entities.items() if v])
            if entities_str:
                context_parts.append(f"Entities Mentioned: {entities_str}")
        
        context_summary = "\n".join(context_parts) if context_parts else "No prior conversation"
        
        classification_prompt = f"""You are an expert intent classifier for an AML database assistant. Analyze this user query in context to understand their TRUE intent.

CURRENT USER QUERY: "{query}"

CONVERSATION HISTORY:
{context_summary}

CRITICAL CLASSIFICATION RULES:
1. If user says "no", "wrong", "not that", "other ones" after a table description → They want DIFFERENT tables (schema intent for NEW table search)
2. If user references "it", "that table", "those columns" → Follow-up about SAME entity (follow_up intent)
3. If user asks clarifying questions about previously shown data → Follow-up intent
4. If query mentions specific NEW table names → Schema intent for that table
5. If query is conversational without database terms → Conversation intent

INTENT CATEGORIES:
- conversation: Small-talk, greetings, identity questions, capabilities inquiry
- schema: Database structure, table/column information, relationships (INCLUDES requests to find OTHER tables)
- data_analysis: Data exploration, counts, null analysis, patterns
- follow_up: Contextual continuation about the SAME entity/table already discussed
- general: Mixed or unclear database-related query
- abuse: Harassment, toxicity, inappropriate content

ENTITY TYPES TO EXTRACT:
- tables: Database table names (extract NEW tables mentioned, or infer from "other tables" context)
- columns: Column names mentioned
- business: Business concepts (customer, transaction, risk, aml, compliance)
- technical: Technical terms (sql, query, schema, index)

EXAMPLES:
- "what is pio_accounts about?" → schema (new table query)
- "no its not their is another ones" (after PIO_ACCOUNTS) → schema (wants OTHER tables, not follow-up)
- "tell me more about it" → follow_up (same table)
- "what about the transactions table?" → schema (new table query)
- "how many records?" → follow_up (if referring to recent table) OR data_analysis

Respond in JSON format:
{{
    "intent": "category",
    "confidence": 0.0-1.0,
    "entities": {{
        "tables": [],
        "columns": [],
        "business": [],
        "technical": []
    }},
    "requires_tools": true/false,
    "context_carryover": [],
    "reasoning": "Brief explanation of why this intent was chosen"
}}"""

        logger.warning(f"LLM DEBUG: Built classification prompt (length: {len(classification_prompt)})")
        logger.warning(f"LLM DEBUG: LLM provider type: {type(self.llm_provider)}")

        try:
            if self.llm_provider:
                logger.warning(f"LLM DEBUG: Calling llm_provider.chat()")
                llm_response = self.llm_provider.chat(
                    messages=[{"role": "user", "content": classification_prompt}],
                    temperature=0.1,
                    max_tokens=300
                )
                
                logger.warning(f"LLM DEBUG: LLM response type: {type(llm_response)}")
                logger.warning(f"LLM DEBUG: LLM response content length: {len(llm_response.content) if hasattr(llm_response, 'content') else 'NO CONTENT ATTR'}")
                logger.warning(f"LLM DEBUG: LLM response content: {llm_response.content[:500] if hasattr(llm_response, 'content') else str(llm_response)[:500]}")
                
                # Parse JSON response from the content attribute
                logger.warning(f"LLM DEBUG: Attempting to parse JSON from LLM response")
                result = json.loads(llm_response.content)
                logger.warning(f"LLM DEBUG: Parsed JSON result: {result}")
                
                classification_result = IntentClassification(
                    intent=IntentType(result.get("intent", "general")),
                    confidence=result.get("confidence", 0.5),
                    entities=result.get("entities", {}),
                    requires_tools=result.get("requires_tools", True),
                    context_carryover=result.get("context_carryover", []),
                    reasoning=result.get("reasoning", "LLM classification")
                )
                
                logger.warning(f"LLM DEBUG: Successfully created IntentClassification: {classification_result.intent.value}")
                return classification_result
            else:
                logger.warning(f"LLM DEBUG: No LLM provider available, falling back")
                
        except Exception as e:
            logger.warning(f"LLM DEBUG: LLM classification failed with exception: {type(e).__name__}: {e}")
            import traceback
            logger.warning(f"LLM DEBUG: Full traceback: {traceback.format_exc()}")
        
        # Fallback to rule-based classification
        return self._fallback_classify(query, session_context)
    
    def _fallback_classify(self, query: str, session_context: Dict[str, Any]) -> IntentClassification:
        """Rule-based fallback when LLM is unavailable."""
        query_lower = query.lower()
        entities = {"tables": [], "columns": [], "business": [], "technical": []}
        
        # Extract entities using simple patterns
        words = query_lower.split()
        for word in words:
            if word.startswith("pio_") or "." in word:
                entities["tables"].append(word.upper())
            elif word in ["customer", "account", "transaction", "risk", "aml"]:
                entities["business"].append(word)
            elif word in ["table", "column", "schema", "sql", "query"]:
                entities["technical"].append(word)
        
        # Determine intent
        if any(word in query_lower for word in ["table", "schema", "structure", "column"]):
            intent = IntentType.SCHEMA
            requires_tools = True
        elif any(word in query_lower for word in ["count", "how many", "null", "analyze"]):
            intent = IntentType.DATA_ANALYSIS
            requires_tools = True
        elif entities["tables"] or entities["business"]:
            intent = IntentType.GENERAL
            requires_tools = True
        else:
            intent = IntentType.CONVERSATION
            requires_tools = False
        
        return IntentClassification(
            intent=intent,
            confidence=0.6,
            entities=entities,
            requires_tools=requires_tools,
            context_carryover=[],
            reasoning="Rule-based fallback classification"
        )


class ConversationMemory:
    """
    Multi-layered memory: short-term sliding window + episodic summaries + long-term knowledge.
    """
    
    def __init__(self, storage_path):
        self.storage_path = Path(storage_path) if isinstance(storage_path, str) else storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # In-memory caches
        self.short_term: Dict[str, List[ConversationTurn]] = {}  # Last 5-10 turns
        self.episodic: Dict[str, Dict[str, Any]] = {}           # Session summaries
        
    def add_turn(self, session_id: str, turn: ConversationTurn) -> None:
        """Add turn to short-term memory and update episodic summary."""
        
        print(f"ADD_TURN: Called for session {session_id}, turn: {turn.query[:50]}...")
        
        # Update short-term sliding window
        if session_id not in self.short_term:
            self.short_term[session_id] = []
        
        self.short_term[session_id].append(turn)
        
        # Keep only last 10 turns
        if len(self.short_term[session_id]) > 10:
            self.short_term[session_id] = self.short_term[session_id][-10:]
        
        # Update episodic summary
        self._update_episodic_summary(session_id, turn)
        
        # Persist to storage
        print(f"ADD_TURN: Persisting session {session_id}...")
        self._persist_session(session_id)
        print(f"ADD_TURN: Session {session_id} persisted successfully")
    
    def get_context(self, session_id: str) -> Dict[str, Any]:
        """Get rich context for intent classification and tool routing."""
        
        print(f'GET_CONTEXT: Called for session {session_id}')
        print(f'GET_CONTEXT: session_id in short_term? {session_id in self.short_term}')
        print(f'GET_CONTEXT: session_id in episodic? {session_id in self.episodic}')
        
        # Load session from storage if not in memory
        if session_id not in self.short_term and session_id not in self.episodic:
            print(f'GET_CONTEXT: Session not in memory, loading from disk...')
            self._load_session(session_id)
        
        recent_turns = self.short_term.get(session_id, [])
        episodic_summary = self.episodic.get(session_id, {})
        print(f'MEMORY DEBUG: recent_turns count: {len(recent_turns)}')
        print(f'MEMORY DEBUG: short_term keys: {list(self.short_term.keys())}')
        
        # Extract recent entities and topics
        recent_entities = {}
        recent_queries = []
        recent_tables = []
        
        for turn in recent_turns[-3:]:  # Last 3 turns
            recent_queries.append(turn.query)
            for entity_type, entities in turn.entities.items():
                if entity_type not in recent_entities:
                    recent_entities[entity_type] = []
                recent_entities[entity_type].extend(entities)
                
                # Track tables specifically for conversation context
                if entity_type == "tables" and entities:
                    recent_tables.extend(entities)
        
        # Deduplicate and keep most recent
        for entity_type in recent_entities:
            recent_entities[entity_type] = list(dict.fromkeys(recent_entities[entity_type]))[-5:]
        
        # Deduplicate recent tables and keep order
        recent_tables = list(dict.fromkeys(recent_tables))
        
        # Get last answer summary (truncate if too long)
        last_answer_summary = ""
        if recent_turns:
            last_turn = recent_turns[-1]
            last_response = last_turn.response if hasattr(last_turn, 'response') else ""
            # Truncate to first 200 chars for context (just need the gist)
            if last_response:
                last_answer_summary = last_response[:200] + ("..." if len(last_response) > 200 else "")
        
        # Get episodic summary
        episodic_text = episodic_summary.get("summary", "")
        
        return {
            "recent_turns": recent_queries,
            "recent_entities": recent_entities,
            "recent_tables": recent_tables,  # NEW: List of recently discussed tables
            "last_answer_summary": last_answer_summary,  # NEW: What system just said
            "episodic_summary": episodic_text,  # NEW: Session summary
            "session_summary": episodic_text,  # Keep for backward compatibility
            "active_topics": episodic_summary.get("active_topics", []),
            "user_preferences": episodic_summary.get("preferences", {}),
            "turn_count": len(recent_turns)
        }
    
    def _update_episodic_summary(self, session_id: str, turn: ConversationTurn) -> None:
        """Update session-level episodic memory."""
        if session_id not in self.episodic:
            self.episodic[session_id] = {
                "summary": "",
                "active_topics": [],
                "preferences": {},
                "key_entities": {},
                "session_start": datetime.utcnow().isoformat()
            }
        
        summary = self.episodic[session_id]
        
        # Track active topics
        if turn.intent in [IntentType.SCHEMA, IntentType.DATA_ANALYSIS]:
            for entity_list in turn.entities.values():
                summary["active_topics"].extend(entity_list)
            # Keep unique, most recent
            summary["active_topics"] = list(dict.fromkeys(summary["active_topics"]))[-10:]
        
        # Accumulate key entities
        for entity_type, entities in turn.entities.items():
            if entity_type not in summary["key_entities"]:
                summary["key_entities"][entity_type] = []
            summary["key_entities"][entity_type].extend(entities)
            # Deduplicate
            summary["key_entities"][entity_type] = list(dict.fromkeys(summary["key_entities"][entity_type]))
        
        # Generate conversation summary
        try:
            # Get all turns for this session
            session_turns = self.short_term.get(session_id, [])
            if len(session_turns) > 0:
                # Create a concise summary of the conversation
                key_tables = summary["key_entities"].get("tables", [])
                key_queries = [t.query for t in session_turns[-3:]]  # Last 3 queries
                
                if key_tables:
                    table_summary = f"Discussed tables: {', '.join(key_tables[:5])}"
                else:
                    table_summary = "General database inquiry"
                
                summary["summary"] = f"{table_summary}. Recent queries: {len(session_turns)} total."
                print(f'EPISODIC: Updated summary for {session_id}: {summary["summary"]}')
        except Exception as e:
            print(f'EPISODIC: Failed to generate summary: {e}')
            summary["summary"] = f"Database conversation with {len(self.short_term.get(session_id, []))} turns"
    
    def _load_session(self, session_id: str) -> None:
        """Load session data from storage into memory."""
        try:
            session_file = self.storage_path / f"session_{session_id}.json"
            print(f'LOAD_SESSION: Checking file {session_file}')
            print(f'LOAD_SESSION: File exists? {session_file.exists()}')
            
            if session_file.exists():
                with open(session_file, 'r') as f:
                    session_data = json.load(f)
                
                # Restore turns to short-term memory
                turns = []
                turns_data = session_data.get("turns", [])
                print(f'LOAD_SESSION: Found {len(turns_data)} turns in file')
                
                for turn_data in turns_data:
                    try:
                        turn = ConversationTurn(
                            turn_id=turn_data["turn_id"],
                            query=turn_data["query"],
                            intent=IntentType(turn_data["intent"]),
                            entities=turn_data["entities"],
                            tools_used=turn_data["tools_used"],
                            response=turn_data["response"],
                            confidence=turn_data["confidence"],
                            timestamp=datetime.fromisoformat(turn_data["timestamp"]),
                            context_inherited=turn_data["context_inherited"]
                        )
                        turns.append(turn)
                    except Exception as turn_error:
                        logger.warning(f"Failed to load turn {turn_data.get('turn_id', 'unknown')}: {turn_error}")
                        # Continue loading other turns
                        continue
                
                self.short_term[session_id] = turns
                print(f'LOAD_SESSION: Loaded {len(turns)} turns into short_term[{session_id}]')
                
                # Restore episodic memory
                episodic = session_data.get("episodic_summary", {})
                self.episodic[session_id] = episodic
                
                logger.info(f"Loaded session {session_id} with {len(turns)} turns")
            else:
                print(f'LOAD_SESSION: File does not exist, initializing empty session')
                # Initialize empty session
                self.short_term[session_id] = []
                self.episodic[session_id] = {
                    "summary": "",
                    "active_topics": [],
                    "preferences": {},
                    "key_entities": {},
                    "session_start": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.warning(f"Failed to load session {session_id}: {e}")
            # Initialize empty session on failure
            self.short_term[session_id] = []
            self.episodic[session_id] = {}
    
    def _persist_session(self, session_id: str) -> None:
        """Persist session data to storage."""
        try:
            session_file = self.storage_path / f"session_{session_id}.json"
            
            # Convert turns to serializable format
            turns_data = []
            for turn in self.short_term.get(session_id, []):
                turns_data.append({
                    "turn_id": turn.turn_id,
                    "query": turn.query,
                    "intent": turn.intent.value,
                    "entities": turn.entities,
                    "tools_used": turn.tools_used,
                    "response": turn.response,
                    "confidence": turn.confidence,
                    "timestamp": turn.timestamp.isoformat(),
                    "context_inherited": turn.context_inherited
                })
            
            session_data = {
                "session_id": session_id,
                "turns": turns_data,
                "episodic_summary": self.episodic.get(session_id, {}),
                "last_updated": datetime.utcnow().isoformat()
            }
            
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to persist session {session_id}: {e}")


class SafetyGuards:
    """
    Safety, governance, and abuse handling for production deployment.
    """
    
    def __init__(self):
        self.abuse_responses = [
            "I'm here to help with AML database questions. What would you like to know about your data?",
            "I focus on database and data analysis tasks. How can I assist you with your AML system?",
            "Let's keep our conversation focused on database queries and data analysis. What can I help you with?"
        ]
    
    def handle_abuse(self, query: str, session_context: Dict[str, Any]) -> str:
        """Brief, neutral response to abuse that redirects to capabilities."""
        import random
        return random.choice(self.abuse_responses)
    
    def validate_sql_safety(self, sql_query: str) -> Dict[str, Any]:
        """Enhanced SQL safety validation."""
        sql_upper = sql_query.upper().strip()
        
        # Forbidden operations
        forbidden_keywords = [
            "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", 
            "TRUNCATE", "GRANT", "REVOKE", "EXECUTE", "CALL"
        ]
        
        for keyword in forbidden_keywords:
            if keyword in sql_upper:
                return {
                    "safe": False,
                    "reason": f"Forbidden operation: {keyword}",
                    "recommendation": "Only SELECT operations are allowed for safety"
                }
        
        # Must start with SELECT
        if not sql_upper.startswith("SELECT"):
            return {
                "safe": False,
                "reason": "Query must start with SELECT",
                "recommendation": "Use SELECT statements for data exploration"
            }
        
        # Check for suspicious patterns
        suspicious_patterns = ["UNION", "EXEC", "--", "/*", "*/"]
        for pattern in suspicious_patterns:
            if pattern in sql_upper:
                return {
                    "safe": False,
                    "reason": f"Suspicious pattern detected: {pattern}",
                    "recommendation": "Avoid complex SQL constructs for safety"
                }
        
        return {"safe": True, "validation_passed": True}
    
    def check_rate_limits(self, session_id: str) -> bool:
        """Simple rate limiting (can be enhanced with Redis)."""
        # Placeholder for rate limiting logic
        return True
