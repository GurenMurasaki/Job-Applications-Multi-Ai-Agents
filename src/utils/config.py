"""
Configuration Loader

Loads and validates configuration from YAML files and environment variables.
"""

import os
from pathlib import Path
from typing import Dict, Any
from loguru import logger


def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file with environment variable overrides.
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        Configuration dictionary
    """
    import yaml
    from dotenv import load_dotenv
    
    # Load .env file
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file)
    
    # Load YAML config
    config_file = Path(config_path)
    if not config_file.exists():
        logger.warning(f"Config file not found: {config_path}, using defaults")
        config = _get_default_config()
    else:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f) or {}
    
    # Apply environment variable overrides
    config = _apply_env_overrides(config)
    
    # Validate and set defaults
    config = _validate_config(config)
    
    return config


def _get_default_config() -> Dict[str, Any]:
    """Get default configuration."""
    return {
        "kafka": {
            "bootstrap_servers": "localhost:9092",
            "group_id": "job-application-agents",
            "topics": ["linkedin-jobs"],
            "consumer_timeout_ms": 30000
        },
        "llm": {
            "provider": "ollama",
            "model": "llama3.2",
            "base_url": "http://localhost:11434",
            "temperature": 0.7,
            "max_tokens": 4096
        },
        "latex": {
            "compiler": "pdflatex",
            "compile_attempts": 2,
            "cleanup_aux_files": True
        },
        "gmail": {
            "credentials_file": "config/gmail_credentials.json",
            "token_file": "config/gmail_token.json",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.compose",
                "https://www.googleapis.com/auth/gmail.modify"
            ]
        },
        "paths": {
            "jobs_dir": "data/jobs",
            "user_dir": "data/user",
            "templates_dir": "templates",
            "processed_dir": "data/processed",
            "user_profile": "config/user_profile.yaml"
        },
        "language": {
            "default": "en",
            "country_mapping": {
                "France": "fr",
                "Belgium": "fr",
                "Switzerland": "fr",
                "Canada": "en",
                "UK": "en",
                "USA": "en"
            }
        },
        "processing": {
            "batch_size": 10,
            "retry_attempts": 3,
            "retry_delay": 5
        }
    }


def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment variable overrides to config."""
    # Kafka
    if os.getenv("KAFKA_BOOTSTRAP_SERVERS"):
        config.setdefault("kafka", {})["bootstrap_servers"] = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
    if os.getenv("KAFKA_GROUP_ID"):
        config.setdefault("kafka", {})["group_id"] = os.getenv("KAFKA_GROUP_ID")
    
    # LLM
    if os.getenv("LLM_PROVIDER"):
        config.setdefault("llm", {})["provider"] = os.getenv("LLM_PROVIDER")
    if os.getenv("LLM_MODEL"):
        config.setdefault("llm", {})["model"] = os.getenv("LLM_MODEL")
    if os.getenv("OLLAMA_BASE_URL"):
        config.setdefault("llm", {})["base_url"] = os.getenv("OLLAMA_BASE_URL")
    if os.getenv("OPENAI_API_KEY"):
        config.setdefault("llm", {})["api_key"] = os.getenv("OPENAI_API_KEY")
    
    # Gmail
    if os.getenv("GMAIL_CREDENTIALS_FILE"):
        config.setdefault("gmail", {})["credentials_file"] = os.getenv("GMAIL_CREDENTIALS_FILE")
    if os.getenv("GMAIL_TOKEN_FILE"):
        config.setdefault("gmail", {})["token_file"] = os.getenv("GMAIL_TOKEN_FILE")
    
    # Paths
    if os.getenv("JOBS_DIR"):
        config.setdefault("paths", {})["jobs_dir"] = os.getenv("JOBS_DIR")
    if os.getenv("USER_DIR"):
        config.setdefault("paths", {})["user_dir"] = os.getenv("USER_DIR")
    if os.getenv("TEMPLATES_DIR"):
        config.setdefault("paths", {})["templates_dir"] = os.getenv("TEMPLATES_DIR")
    
    return config


def _validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate configuration and set missing defaults."""
    defaults = _get_default_config()
    
    # Deep merge with defaults
    def deep_merge(base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    config = deep_merge(defaults, config)
    
    # Ensure required paths exist
    paths = config.get("paths", {})
    for key in ["jobs_dir", "user_dir", "templates_dir", "processed_dir"]:
        path = Path(paths.get(key, ""))
        if path and not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory: {path}")
    
    return config
