"""
Logger Setup

Configures loguru for consistent logging across the application.
"""

import sys
from pathlib import Path
from loguru import logger


def setup_logger(level: str = "INFO", log_dir: str = "logs"):
    """
    Setup loguru logger with console and file handlers.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
    """
    # Remove default handler
    logger.remove()
    
    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Console handler with colors
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        colorize=True
    )
    
    # File handler for all logs
    logger.add(
        log_path / "job_agents.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention="1 week",
        compression="zip"
    )
    
    # Separate file for errors
    logger.add(
        log_path / "errors.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention="1 month"
    )
    
    logger.info(f"Logger initialized with level: {level}")
