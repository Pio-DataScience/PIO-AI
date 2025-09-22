"""
LLM provider abstraction with OpenAI, Azure OpenAI, and local model support.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod
from dotenv import load_dotenv

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "config", ".env"))


@dataclass
class LLMConfig:
    """Configuration for LLM providers."""
    provider: str   # openai | azure_openai | cohere | local
    model: str
    base_url: str | None = None
    api_key: str | None = None
    azure_deployment: str | None = None


@dataclass
class LLMResponse:
    """Response from LLM with metadata."""
    content: str
    model: str
    tokens_used: Optional[int] = None
    finish_reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """Send chat messages and get response."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available/configured."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self._client = None
    
    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("OpenAI library not installed. Run: pip install openai")
        return self._client
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """Send chat messages to OpenAI."""
        if not self.is_available():
            raise ValueError("OpenAI API key not configured")
        
        client = self._get_client()
        
        # Default parameters
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 1500),
        }
        
        try:
            response = client.chat.completions.create(**params)
            
            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model,
                tokens_used=response.usage.total_tokens if response.usage else None,
                finish_reason=response.choices[0].finish_reason,
                metadata={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                    "completion_tokens": response.usage.completion_tokens if response.usage else None,
                }
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")
    
    def is_available(self) -> bool:
        """Check if OpenAI is configured."""
        return bool(self.api_key)


class AzureOpenAIProvider(LLMProvider):
    """Azure OpenAI API provider."""
    
    def __init__(self, api_key: Optional[str] = None, endpoint: Optional[str] = None, 
                 deployment: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.deployment = deployment
        self._client = None
    
    def _get_client(self):
        """Lazy initialization of Azure OpenAI client."""
        if self._client is None:
            try:
                import openai
                self._client = openai.AzureOpenAI(
                    api_key=self.api_key,
                    azure_endpoint=self.endpoint,
                    api_version="2024-02-01"
                )
            except ImportError:
                raise ImportError("OpenAI library not installed. Run: pip install openai")
        return self._client
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """Send chat messages to Azure OpenAI."""
        if not self.is_available():
            raise ValueError("Azure OpenAI not configured")
        
        client = self._get_client()
        
        params = {
            "model": self.deployment,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 1500),
        }
        
        try:
            response = client.chat.completions.create(**params)
            
            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model,
                tokens_used=response.usage.total_tokens if response.usage else None,
                finish_reason=response.choices[0].finish_reason,
                metadata={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                    "completion_tokens": response.usage.completion_tokens if response.usage else None,
                    "provider": "azure_openai"
                }
            )
        except Exception as e:
            raise RuntimeError(f"Azure OpenAI API error: {e}")
    
    def is_available(self) -> bool:
        """Check if Azure OpenAI is configured."""
        return bool(self.api_key and self.endpoint)


class CohereProvider(LLMProvider):
    """Cohere API provider."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "command-r-08-2024"):
        self.api_key = api_key or os.getenv("COHERE_API_KEY")
        self.model = model or os.getenv("COHERE_MODEL", "command-r-08-2024")
        self._client = None
    
    def _get_client(self):
        """Lazy initialization of Cohere client."""
        if self._client is None:
            try:
                import cohere
                self._client = cohere.Client(api_key=self.api_key)
            except ImportError:
                raise ImportError("Cohere library not installed. Run: pip install cohere")
        return self._client
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """Send chat messages to Cohere."""
        if not self.is_available():
            raise ValueError("Cohere API key not configured")
        
        client = self._get_client()
        
        # Convert messages to Cohere format
        # Cohere uses a different format - separate system message and chat history
        system_message = ""
        chat_history = []
        user_message = ""
        
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            elif msg["role"] == "user":
                user_message = msg["content"]
            elif msg["role"] == "assistant":
                chat_history.append({"role": "CHATBOT", "message": msg["content"]})
        
        # Default parameters
        params = {
            "model": self.model,
            "message": user_message,
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 1500),
        }
        
        if system_message:
            params["preamble"] = system_message
        
        if chat_history:
            params["chat_history"] = chat_history
        
        try:
            response = client.chat(**params)
            
            # Extract token usage if available
            tokens_used = None
            if hasattr(response, 'meta') and response.meta:
                if hasattr(response.meta, 'tokens'):
                    tokens_used = (response.meta.tokens.input_tokens + 
                                 response.meta.tokens.output_tokens)
            
            return LLMResponse(
                content=response.text,
                model=self.model,
                tokens_used=tokens_used,
                finish_reason="stop",  # Cohere doesn't provide finish_reason in the same way
                metadata={
                    "provider": "cohere",
                    "generation_id": getattr(response, 'generation_id', None),
                    "response_id": getattr(response, 'response_id', None)
                }
            )
        except Exception as e:
            raise RuntimeError(f"Cohere API error: {e}")
    
    def is_available(self) -> bool:
        """Check if Cohere is configured."""
        return bool(self.api_key)


class LocalProvider(LLMProvider):
    """Local model provider via OpenAI-compatible API."""
    
    def __init__(self, base_url: Optional[str] = None, model: str = "qwen2.5-7b-instruct-q4_k_m"):
        self.base_url = base_url or os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
        self.model = model
        self._client = None
    
    def _get_client(self):
        """Lazy initialization of local client."""
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI(
                    base_url=self.base_url,
                    api_key="dummy"  # Local servers often don't need real keys
                )
            except ImportError:
                raise ImportError("OpenAI library not installed. Run: pip install openai")
        return self._client
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """Send chat to local model."""
        if not self.is_available():
            # Return a stub response for development
            return LLMResponse(
                content="[LOCAL MODEL STUB] This would be the response from a local model.",
                model=f"local-{self.model}",
                tokens_used=100,
                finish_reason="stop",
                metadata={"provider": "local", "stub": True}
            )
        
        client = self._get_client()
        
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 1500),
        }
        
        try:
            response = client.chat.completions.create(**params)
            
            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model,
                tokens_used=response.usage.total_tokens if response.usage else None,
                finish_reason=response.choices[0].finish_reason,
                metadata={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                    "completion_tokens": response.usage.completion_tokens if response.usage else None,
                    "provider": "local"
                }
            )
        except Exception as e:
            # Return stub on connection error
            return LLMResponse(
                content=f"[LOCAL MODEL UNAVAILABLE] {e}",
                model=f"local-{self.model}",
                tokens_used=0,
                finish_reason="error",
                metadata={"provider": "local", "error": str(e)}
            )
    
    def is_available(self) -> bool:
        """Check if local model is available."""
        try:
            import requests
            response = requests.get(f"{self.base_url.rstrip('/v1')}/health", timeout=2)
            return response.status_code == 200
        except:
            return False


class LLMManager:
    """Manages multiple LLM providers with fallback."""
    
    def __init__(self):
        # Load configuration
        config = load_llm_config()
        
        # Initialize providers
        self.providers: Dict[str, LLMProvider] = {
            "openai": OpenAIProvider(),
            "azure_openai": AzureOpenAIProvider(),
            "cohere": CohereProvider(),
            "local": LocalProvider(),
        }
        
        self.default_provider = config.provider
    
    def set_default_provider(self, provider_name: str):
        """Set the default provider."""
        if provider_name not in self.providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        self.default_provider = provider_name
    
    def add_provider(self, name: str, provider: LLMProvider):
        """Add a custom provider."""
        self.providers[name] = provider
    
    def chat(self, messages: List[Dict[str, str]], provider: Optional[str] = None, 
             **kwargs) -> LLMResponse:
        """
        Send chat messages using specified or default provider.
        
        Args:
            messages: List of chat messages
            provider: Provider name (optional, uses default if not specified)
            **kwargs: Additional parameters for the provider
            
        Returns:
            LLMResponse from the provider
        """
        provider_name = provider or self.default_provider
        
        if provider_name not in self.providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        
        llm_provider = self.providers[provider_name]
        
        # Try the specified provider
        if llm_provider.is_available():
            try:
                return llm_provider.chat(messages, **kwargs)
            except Exception as e:
                print(f"Warning: {provider_name} provider failed: {e}")
                # Fall through to fallback logic
        
        # Fallback to any available provider
        for name, fallback_provider in self.providers.items():
            if name != provider_name and fallback_provider.is_available():
                try:
                    print(f"Falling back to {name} provider")
                    response = fallback_provider.chat(messages, **kwargs)
                    response.metadata = response.metadata or {}
                    response.metadata["fallback_from"] = provider_name
                    return response
                except Exception as e:
                    print(f"Warning: {name} fallback failed: {e}")
                    continue
        
        # If all providers fail, return a stub response
        return LLMResponse(
            content="Sorry, no LLM providers are currently available. Please configure an API key or local model.",
            model="stub",
            tokens_used=0,
            finish_reason="error",
            metadata={"error": "no_providers_available"}
        )
    
    def get_available_providers(self) -> List[str]:
        """Get list of available providers."""
        return [name for name, provider in self.providers.items() if provider.is_available()]


def load_llm_config() -> LLMConfig:
    """Load LLM configuration from environment."""
    provider = os.getenv("PROVIDER", "openai").lower()
    if provider == "openai":
        return LLMConfig(provider="openai",
                         model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                         api_key=os.getenv("OPENAI_API_KEY"))
    elif provider == "azure_openai":
        return LLMConfig(provider="azure_openai",
                         model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                         api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                         base_url=os.getenv("AZURE_OPENAI_ENDPOINT"))
    elif provider == "cohere":
        return LLMConfig(provider="cohere",
                         model=os.getenv("COHERE_MODEL", "command-r-plus"),
                         api_key=os.getenv("COHERE_API_KEY"))
    else:
        return LLMConfig(provider="local",
                         model=os.getenv("LOCAL_LLM_MODEL", "qwen2.5-7b-instruct-q4_k_m"),
                         base_url=os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8000/v1"))


# Global instance
llm_manager = LLMManager()


# Convenience functions
def chat(messages: List[Dict[str, str]], provider: Optional[str] = None, **kwargs) -> LLMResponse:
    """Send chat messages using the global LLM manager."""
    return llm_manager.chat(messages, provider, **kwargs)


def set_provider(provider_name: str):
    """Set the default provider globally."""
    llm_manager.set_default_provider(provider_name)


def get_available_providers() -> List[str]:
    """Get available providers."""
    return llm_manager.get_available_providers()


def configure_openai(api_key: str, model: str = "gpt-4o-mini"):
    """Configure OpenAI provider."""
    llm_manager.providers["openai"] = OpenAIProvider(api_key, model)


def configure_azure_openai(api_key: str, endpoint: str, deployment: str = "gpt-4o-mini"):
    """Configure Azure OpenAI provider."""
    llm_manager.providers["azure_openai"] = AzureOpenAIProvider(api_key, endpoint, deployment)


def configure_cohere(api_key: str, model: str = "command-r-plus"):
    """Configure Cohere provider."""
    llm_manager.providers["cohere"] = CohereProvider(api_key, model)


def configure_local(base_url: str, model: str = "qwen2.5-7b-instruct-q4_k_m"):
    """Configure local provider."""
    llm_manager.providers["local"] = LocalProvider(base_url, model)
