"""
Enhanced multi-tier conversation memory system with observability integration.
Implements short-term buffer, episodic summarization, and long-term persistence.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from collections import deque
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """Single conversation turn with full context."""
    turn_id: str
    session_id: str
    timestamp: datetime
    user_query: str
    agent_response: str
    intent: Optional[str] = None
    entities: List[str] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationTurn':
        """Create from dictionary."""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class EpisodicMemory:
    """Summarized memory of conversation episodes."""
    episode_id: str
    session_id: str
    start_time: datetime
    end_time: datetime
    turn_count: int
    summary: str
    key_entities: List[str]
    topics: List[str]
    important_facts: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        d['start_time'] = self.start_time.isoformat()
        d['end_time'] = self.end_time.isoformat()
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EpisodicMemory':
        """Create from dictionary."""
        data['start_time'] = datetime.fromisoformat(data['start_time'])
        data['end_time'] = datetime.fromisoformat(data['end_time'])
        return cls(**data)


class EnhancedConversationMemory:
    """
    Multi-tier conversation memory system with observability.
    
    Tiers:
    1. Short-term: Last N turns in memory (sliding window)
    2. Episodic: Summarized themes and entities from recent conversation
    3. Long-term: Persistent storage across sessions
    """
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        short_term_window: int = 10,
        episodic_threshold: int = 5,
        storage_path: Optional[Path] = None,
        enable_observability: bool = True,
        llm_summarizer: Optional[Any] = None
    ):
        """
        Initialize enhanced memory system.
        
        Args:
            session_id: Unique session identifier
            short_term_window: Number of recent turns to keep in short-term memory
            episodic_threshold: Number of turns before creating episodic summary
            storage_path: Path for long-term storage
            enable_observability: Enable structured logging
            llm_summarizer: LLM client for generating summaries
        """
        self.session_id = session_id or str(uuid.uuid4())
        self.short_term_window = short_term_window
        self.episodic_threshold = episodic_threshold
        self.enable_observability = enable_observability
        self.llm_summarizer = llm_summarizer
        
        # Short-term memory: Recent turns
        self.short_term: deque = deque(maxlen=short_term_window)
        
        # Episodic memory: Summarized episodes
        self.episodic: List[EpisodicMemory] = []
        
        # Active entities and topics
        self.active_entities: Dict[str, int] = {}  # entity -> mention count
        self.active_topics: List[str] = []
        
        # Long-term storage
        self.storage_path = storage_path or Path("memory/sessions")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Load existing session if available
        self._load_session()
        
        logger.info(
            f"Enhanced memory initialized for session {self.session_id}",
            extra={
                "operation": "memory.init",
                "session_id": self.session_id,
                "short_term_window": short_term_window,
                "episodic_threshold": episodic_threshold
            }
        )
    
    def add_turn(
        self,
        user_query: str,
        agent_response: str,
        intent: Optional[str] = None,
        entities: Optional[List[str]] = None,
        tools_used: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ) -> ConversationTurn:
        """
        Add a conversation turn to memory with observability.
        
        Args:
            user_query: User's input
            agent_response: Agent's response
            intent: Classified intent
            entities: Extracted entities
            tools_used: List of tools invoked
            metadata: Additional context
            trace_id: Tracing identifier
            
        Returns:
            Created ConversationTurn
        """
        turn = ConversationTurn(
            turn_id=str(uuid.uuid4()),
            session_id=self.session_id,
            timestamp=datetime.now(),
            user_query=user_query,
            agent_response=agent_response,
            intent=intent,
            entities=entities or [],
            tools_used=tools_used or [],
            metadata=metadata or {},
            trace_id=trace_id or str(uuid.uuid4())
        )
        
        # Add to short-term memory
        self.short_term.append(turn)
        
        # Update active entities
        for entity in turn.entities:
            self.active_entities[entity] = self.active_entities.get(entity, 0) + 1
        
        # Update active topics if intent provided
        if intent and intent not in self.active_topics:
            self.active_topics.append(intent)
            if len(self.active_topics) > 5:
                self.active_topics.pop(0)
        
        # Observability logging
        if self.enable_observability:
            logger.info(
                f"Conversation turn saved: {turn.turn_id}",
                extra={
                    "operation": "memory.save_turn",
                    "session_id": self.session_id,
                    "turn_id": turn.turn_id,
                    "trace_id": turn.trace_id,
                    "intent": intent,
                    "entities": entities,
                    "tools_used": tools_used,
                    "query_length": len(user_query),
                    "response_length": len(agent_response)
                }
            )
        
        # Check if episodic summary needed
        if len(self.short_term) >= self.episodic_threshold:
            self._create_episodic_summary()
        
        # Persist to long-term storage
        self._save_turn(turn)
        
        return turn
    
    def get_recent_context(self, max_turns: Optional[int] = None) -> str:
        """
        Get recent conversation context as formatted text.
        
        Args:
            max_turns: Maximum number of turns to include
            
        Returns:
            Formatted conversation context
        """
        turns = list(self.short_term)
        if max_turns:
            turns = turns[-max_turns:]
        
        if not turns:
            return ""
        
        context_parts = []
        for turn in turns:
            context_parts.append(f"User: {turn.user_query}")
            context_parts.append(f"Assistant: {turn.agent_response}")
        
        return "\n".join(context_parts)
    
    def get_episodic_summary(self) -> str:
        """
        Get episodic memory summary.
        
        Returns:
            Formatted summary of recent episodes
        """
        if not self.episodic:
            return ""
        
        summaries = []
        for episode in self.episodic[-3:]:  # Last 3 episodes
            summaries.append(f"Topic: {', '.join(episode.topics)}")
            summaries.append(f"Summary: {episode.summary}")
            if episode.important_facts:
                summaries.append(f"Key facts: {'; '.join(episode.important_facts)}")
        
        return "\n\n".join(summaries)
    
    def get_active_entities(self, top_n: int = 10) -> List[Tuple[str, int]]:
        """
        Get most frequently mentioned entities.
        
        Args:
            top_n: Number of top entities to return
            
        Returns:
            List of (entity, count) tuples
        """
        sorted_entities = sorted(
            self.active_entities.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_entities[:top_n]
    
    def get_full_context(self, include_episodic: bool = True) -> Dict[str, Any]:
        """
        Get comprehensive memory context for LLM prompting.
        
        Args:
            include_episodic: Include episodic summaries
            
        Returns:
            Dictionary with all context
        """
        context = {
            "session_id": self.session_id,
            "recent_conversation": self.get_recent_context(),
            "active_entities": [entity for entity, _ in self.get_active_entities()],
            "active_topics": self.active_topics,
            "turn_count": len(self.short_term)
        }
        
        if include_episodic and self.episodic:
            context["episodic_summary"] = self.get_episodic_summary()
        
        return context
    
    def find_similar_past_queries(self, query: str, max_results: int = 3) -> List[ConversationTurn]:
        """
        Find similar past queries from long-term memory.
        
        Args:
            query: Current query
            max_results: Maximum number of results
            
        Returns:
            List of similar past turns
        """
        # Simple implementation: keyword matching
        # In production, use vector similarity
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        similar_turns = []
        
        # Check recent turns first
        for turn in self.short_term:
            turn_words = set(turn.user_query.lower().split())
            overlap = len(query_words & turn_words)
            if overlap >= 2:  # At least 2 word overlap
                similar_turns.append((turn, overlap))
        
        # Sort by overlap and return
        similar_turns.sort(key=lambda x: x[1], reverse=True)
        return [turn for turn, _ in similar_turns[:max_results]]
    
    def clear_short_term(self):
        """Clear short-term memory (useful for context switching)."""
        if self.enable_observability:
            logger.info(
                "Clearing short-term memory",
                extra={
                    "operation": "memory.clear_short_term",
                    "session_id": self.session_id,
                    "turns_cleared": len(self.short_term)
                }
            )
        self.short_term.clear()
    
    def prune_and_summarize(self):
        """
        Manually trigger pruning and summarization.
        Create episodic summary and clear old short-term memory.
        """
        if len(self.short_term) > 0:
            self._create_episodic_summary()
            
            # Keep only most recent turns
            keep_count = min(3, self.short_term_window // 2)
            recent = list(self.short_term)[-keep_count:]
            self.short_term.clear()
            for turn in recent:
                self.short_term.append(turn)
            
            if self.enable_observability:
                logger.info(
                    "Memory pruned and summarized",
                    extra={
                        "operation": "memory.prune",
                        "session_id": self.session_id,
                        "turns_kept": len(self.short_term),
                        "episodes": len(self.episodic)
                    }
                )
    
    def _create_episodic_summary(self):
        """Create episodic summary from recent turns."""
        if not self.short_term:
            return
        
        turns = list(self.short_term)
        start_time = turns[0].timestamp
        end_time = turns[-1].timestamp
        
        # Collect entities and topics
        all_entities = []
        all_topics = []
        for turn in turns:
            all_entities.extend(turn.entities)
            if turn.intent:
                all_topics.append(turn.intent)
        
        # Deduplicate and get most common
        key_entities = list(set(all_entities))[:10]
        topics = list(set(all_topics))
        
        # Generate summary using LLM if available
        summary = self._generate_summary(turns)
        
        # Extract important facts (simplified)
        important_facts = []
        for turn in turns:
            if turn.metadata.get("has_data", False):
                important_facts.append(f"Data retrieved about: {turn.metadata.get('topic', 'unknown')}")
        
        episode = EpisodicMemory(
            episode_id=str(uuid.uuid4()),
            session_id=self.session_id,
            start_time=start_time,
            end_time=end_time,
            turn_count=len(turns),
            summary=summary,
            key_entities=key_entities,
            topics=topics,
            important_facts=important_facts[:5]
        )
        
        self.episodic.append(episode)
        
        # Keep only last N episodes in memory
        if len(self.episodic) > 10:
            self.episodic = self.episodic[-10:]
        
        if self.enable_observability:
            logger.info(
                f"Episodic summary created: {episode.episode_id}",
                extra={
                    "operation": "memory.create_episode",
                    "session_id": self.session_id,
                    "episode_id": episode.episode_id,
                    "turn_count": episode.turn_count,
                    "topics": topics,
                    "entities": key_entities[:5]
                }
            )
        
        # Save episode to long-term storage
        self._save_episode(episode)
    
    def _generate_summary(self, turns: List[ConversationTurn]) -> str:
        """
        Generate natural language summary using LLM.
        
        Args:
            turns: List of conversation turns
            
        Returns:
            Summary text
        """
        if not self.llm_summarizer:
            # Fallback: simple concatenation
            topics = set()
            for turn in turns:
                if turn.intent:
                    topics.add(turn.intent)
            return f"Discussion about {', '.join(topics)}" if topics else "General conversation"
        
        # Use LLM to generate summary
        try:
            conversation_text = "\n".join([
                f"User: {turn.user_query}\nAssistant: {turn.agent_response}"
                for turn in turns
            ])
            
            prompt = f"""Summarize the following conversation in 2-3 sentences, focusing on the main topics and key information discussed:

{conversation_text}

Summary:"""
            
            summary = self.llm_summarizer.generate(prompt, max_tokens=150)
            return summary.strip()
        except Exception as e:
            logger.warning(f"Failed to generate LLM summary: {e}")
            return "Recent conversation episode"
    
    def _save_turn(self, turn: ConversationTurn):
        """Save turn to long-term storage."""
        try:
            session_file = self.storage_path / f"{self.session_id}.jsonl"
            with open(session_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(turn.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to save turn to storage: {e}")
    
    def _save_episode(self, episode: EpisodicMemory):
        """Save episode to long-term storage."""
        try:
            episodes_file = self.storage_path / f"{self.session_id}_episodes.jsonl"
            with open(episodes_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(episode.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to save episode to storage: {e}")
    
    def _load_session(self):
        """Load existing session from long-term storage."""
        try:
            session_file = self.storage_path / f"{self.session_id}.jsonl"
            if not session_file.exists():
                return
            
            # Load turns
            with open(session_file, 'r', encoding='utf-8') as f:
                for line in f:
                    turn_data = json.loads(line)
                    turn = ConversationTurn.from_dict(turn_data)
                    self.short_term.append(turn)
                    
                    # Restore entities
                    for entity in turn.entities:
                        self.active_entities[entity] = self.active_entities.get(entity, 0) + 1
            
            # Load episodes
            episodes_file = self.storage_path / f"{self.session_id}_episodes.jsonl"
            if episodes_file.exists():
                with open(episodes_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        episode_data = json.loads(line)
                        episode = EpisodicMemory.from_dict(episode_data)
                        self.episodic.append(episode)
            
            logger.info(
                f"Session loaded: {len(self.short_term)} turns, {len(self.episodic)} episodes",
                extra={
                    "operation": "memory.load_session",
                    "session_id": self.session_id,
                    "turn_count": len(self.short_term),
                    "episode_count": len(self.episodic)
                }
            )
        except Exception as e:
            logger.error(f"Failed to load session: {e}")


def create_memory_for_session(
    session_id: Optional[str] = None,
    llm_client: Optional[Any] = None,
    **kwargs
) -> EnhancedConversationMemory:
    """
    Factory function to create memory instance.
    
    Args:
        session_id: Session identifier
        llm_client: LLM client for summarization
        **kwargs: Additional configuration
        
    Returns:
        Configured EnhancedConversationMemory instance
    """
    return EnhancedConversationMemory(
        session_id=session_id,
        llm_summarizer=llm_client,
        **kwargs
    )
