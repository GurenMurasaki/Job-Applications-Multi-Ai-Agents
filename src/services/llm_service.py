"""
LLM Service

Handles interaction with LLM providers (Ollama, OpenAI) for
CV customization and cover letter generation.
"""

from typing import Optional, Dict, Any
from loguru import logger


class LLMService:
    """
    Service for interacting with LLM providers.
    
    Supports:
    - Ollama (local)
    - OpenAI API
    - Per-agent model configuration
    """
    
    def __init__(self, config: dict, agent_name: str = None):
        """
        Initialize the LLM service.
        
        Args:
            config: LLM configuration dictionary
            agent_name: Optional agent name for per-agent config
                        Options: "cv_customizer", "cover_letter", "profile_updater"
        """
        # Start with default configuration
        self.provider = config.get("provider", "ollama")
        self.model = config.get("model", "llama3.2")
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.api_key = config.get("api_key", "")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 4096)
        self.timeout = config.get("timeout", 120)
        
        # Check for per-agent configuration
        self.agent_name = agent_name
        if agent_name:
            self._apply_agent_config(config, agent_name)
        
        self._client = None
        self._initialize_client()
    
    def _apply_agent_config(self, config: dict, agent_name: str):
        """Apply per-agent configuration overrides."""
        agents_config = config.get("agents", {})
        agent_config = agents_config.get(agent_name, {})
        
        # Only apply if enabled
        if not agent_config.get("enabled", False):
            logger.debug(f"Using default LLM config for {agent_name}")
            return
        
        # Override with agent-specific settings
        if "model" in agent_config:
            self.model = agent_config["model"]
        if "provider" in agent_config:
            self.provider = agent_config["provider"]
        if "temperature" in agent_config:
            self.temperature = agent_config["temperature"]
        if "max_tokens" in agent_config:
            self.max_tokens = agent_config["max_tokens"]
        if "base_url" in agent_config:
            self.base_url = agent_config["base_url"]
        if "api_key" in agent_config:
            self.api_key = agent_config["api_key"]
        
        logger.info(f"Using custom LLM for {agent_name}: {self.provider}/{self.model}")
    
    def _initialize_client(self):
        """Initialize the appropriate LLM client."""
        if self.provider == "ollama":
            self._init_ollama()
        elif self.provider == "openai":
            self._init_openai()
        else:
            logger.warning(f"Unknown LLM provider: {self.provider}")
    
    def _init_ollama(self):
        """Initialize Ollama client."""
        try:
            import ollama
            self._client = ollama.Client(host=self.base_url)
            logger.info(f"Ollama client initialized: {self.base_url}")
        except ImportError:
            logger.error("ollama package not installed")
        except Exception as e:
            logger.error(f"Failed to initialize Ollama: {e}")
    
    def _init_openai(self):
        """Initialize OpenAI client."""
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
            logger.info("OpenAI client initialized")
        except ImportError:
            logger.error("openai package not installed")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI: {e}")
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Generate text using the configured LLM.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            
        Returns:
            Generated text response
        """
        if self.provider == "ollama":
            return self._generate_ollama(prompt, system_prompt)
        elif self.provider == "openai":
            return self._generate_openai(prompt, system_prompt)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _generate_ollama(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate using Ollama."""
        if not self._client:
            raise RuntimeError("Ollama client not initialized")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self._client.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise
    
    def _generate_openai(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate using OpenAI."""
        if not self._client:
            raise RuntimeError("OpenAI client not initialized")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            raise
    
    def is_available(self) -> bool:
        """Check if the LLM service is available."""
        if self.provider == "ollama":
            return self._check_ollama()
        elif self.provider == "openai":
            return self._client is not None
        return False
    
    def _check_ollama(self) -> bool:
        """Check if Ollama is available."""
        if not self._client:
            return False
        
        try:
            # Try to list models
            self._client.list()
            return True
        except Exception:
            return False
