"""
LLM Engine - Abstracts different LLM providers
Supports Gemini (Vertex AI), Ollama, and others
Last Updated: 2026-05-09
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Represents a conversation message"""
    role: str  # "user" or "assistant"
    content: str


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    @abstractmethod
    def generate_response(self, messages: List[Message], max_tokens: int = 500) -> str:
        """
        Generate response from conversation messages.
        
        Args:
            messages: Conversation history
            max_tokens: Maximum tokens in response
            
        Returns:
            Generated text response
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and available"""
        pass


class GeminiVertexProvider(LLMProvider):
    """Google Gemini via Vertex AI"""
    
    def __init__(self, project_id: Optional[str] = None, model: str = "gemini-1.5-flash"):
        """
        Initialize Gemini Vertex provider.
        
        Args:
            project_id: Google Cloud project ID (uses GOOGLE_CLOUD_PROJECT_ID env var if None)
            model: Model name (gemini-1.5-flash, gemini-1.5-pro, etc.)
        """
        try:
            from langchain_google_vertexai import ChatVertexAI
            
            self.project_id = project_id
            self.model = model
            self.llm = ChatVertexAI(
                project=project_id,
                model=model,
                temperature=0.7,
                max_output_tokens=500,
                top_p=0.95,
            )
            self._available = True
            logger.info(f"✓ Gemini Vertex AI ready (model: {model})")
        except Exception as e:
            self._available = False
            logger.error(f"Failed to initialize Gemini Vertex: {e}")
    
    def generate_response(self, messages: List[Message], max_tokens: int = 500) -> str:
        """Generate response using Gemini"""
        if not self._available:
            return "LLM not available. Using fallback response."
        
        try:
            # Convert Message objects to langchain format
            from langchain_core.messages import HumanMessage, AIMessage
            
            lc_messages = []
            for msg in messages:
                if msg.role == "user":
                    lc_messages.append(HumanMessage(content=msg.content))
                else:
                    lc_messages.append(AIMessage(content=msg.content))
            
            # Generate response
            response = self.llm.invoke(lc_messages)
            return response.content
        
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I encountered an error processing your request. Please try again."
    
    def is_available(self) -> bool:
        """Check if Gemini is available"""
        return self._available


class OllamaProvider(LLMProvider):
    """Local Ollama LLM provider"""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "mistral"):
        """
        Initialize Ollama provider.
        
        Args:
            base_url: Ollama server URL
            model: Model name (mistral, llama2, neural-chat, etc.)
        """
        try:
            from langchain_community.llms import Ollama
            
            self.base_url = base_url
            self.model = model
            self.llm = Ollama(
                base_url=base_url,
                model=model,
            )
            self._available = True
            logger.info(f"✓ Ollama ready (model: {model}, url: {base_url})")
        except Exception as e:
            self._available = False
            logger.warning(f"Ollama not available: {e}")
    
    def generate_response(self, messages: List[Message], max_tokens: int = 500) -> str:
        """Generate response using Ollama"""
        if not self._available:
            return "Local LLM not available. Check Ollama connection."
        
        try:
            # Build prompt from conversation
            prompt = self._build_prompt(messages)
            response = self.llm.invoke(prompt)
            return response.strip()
        
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "Failed to generate response from local LLM."
    
    def is_available(self) -> bool:
        """Check if Ollama is available"""
        return self._available
    
    @staticmethod
    def _build_prompt(messages: List[Message]) -> str:
        """Build prompt from conversation history"""
        prompt_parts = []
        for msg in messages:
            if msg.role == "user":
                prompt_parts.append(f"User: {msg.content}")
            else:
                prompt_parts.append(f"Assistant: {msg.content}")
        prompt_parts.append("Assistant:")
        return "\n".join(prompt_parts)


class FallbackProvider(LLMProvider):
    """Fallback provider with simple template responses"""
    
    def __init__(self):
        """Initialize fallback provider"""
        self.responses = {
            "move": "I'll move the robot for you.",
            "sit": "I'm sitting down now.",
            "stand": "Standing up.",
            "look": "Let me look around.",
        }
        logger.info("✓ Fallback LLM provider ready")
    
    def generate_response(self, messages: List[Message], max_tokens: int = 500) -> str:
        """Generate simple template response"""
        if not messages:
            return "Hello! How can I help you?"
        
        # Get last user message
        user_message = messages[-1].content.lower()
        
        # Simple keyword matching
        for key, response in self.responses.items():
            if key in user_message:
                return response
        
        # Default response
        return f"I heard: {messages[-1].content}. How can I help?"
    
    def is_available(self) -> bool:
        """Fallback is always available"""
        return True


def create_llm_provider(
    provider_name: str = "gemini",
    **kwargs
) -> LLMProvider:
    """
    Factory function to create LLM provider.
    
    Args:
        provider_name: "gemini", "ollama", or "fallback"
        **kwargs: Provider-specific arguments
        
    Returns:
        LLMProvider instance
    """
    providers = {
        "gemini": GeminiVertexProvider,
        "ollama": OllamaProvider,
        "fallback": FallbackProvider,
    }
    
    if provider_name not in providers:
        logger.warning(f"Unknown provider: {provider_name}, using fallback")
        return FallbackProvider()
    
    try:
        provider_class = providers[provider_name]
        
        if provider_name == "gemini":
            # Gemini-specific initialization
            return GeminiVertexProvider(
                project_id=kwargs.get("project_id"),
                model=kwargs.get("model", "gemini-1.5-flash")
            )
        elif provider_name == "ollama":
            # Ollama-specific initialization
            return OllamaProvider(
                base_url=kwargs.get("base_url", "http://localhost:11434"),
                model=kwargs.get("model", "mistral")
            )
        else:
            return provider_class()
    except Exception as e:
        logger.error(f"Failed to create {provider_name} provider: {e}")
        return FallbackProvider()
