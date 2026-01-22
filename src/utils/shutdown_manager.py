"""
Shutdown Manager for the Job Application Multi-Agent System.

Handles graceful and force shutdown signals to ensure proper cleanup
and resumability of job processing.
"""

import signal
import threading
from pathlib import Path
from loguru import logger
from typing import Callable, Optional


class ShutdownManager:
    """
    Manages graceful and force shutdown of the agent system.
    
    Graceful shutdown: Finish current job, then stop
    Force shutdown: Stop immediately (job will resume on restart)
    """
    
    # Singleton instance
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._stop_requested = False
        self._force_stop = False
        self._current_job_id: Optional[str] = None
        self._on_shutdown_callbacks: list[Callable] = []
        
        # File-based stop signal (for stop.sh script)
        self._stop_file = Path(".stop_requested")
        self._pid_file = Path(".agent.pid")
        
        # Register signal handlers
        self._register_signals()
    
    def _register_signals(self):
        """Register signal handlers for graceful and force shutdown."""
        # SIGTERM - graceful shutdown (finish current job)
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        
        # SIGINT (Ctrl+C) - graceful shutdown
        signal.signal(signal.SIGINT, self._handle_sigint)
        
        # SIGUSR1 - check stop file (can be used for polling)
        try:
            signal.signal(signal.SIGUSR1, self._handle_sigusr1)
        except (AttributeError, ValueError):
            # SIGUSR1 not available on Windows
            pass
    
    def _handle_sigterm(self, signum, frame):
        """Handle SIGTERM - graceful shutdown."""
        logger.warning("Received SIGTERM - initiating graceful shutdown...")
        self._stop_requested = True
        
        if self._current_job_id:
            logger.info(f"Will stop after completing current job: {self._current_job_id}")
        else:
            logger.info("No job in progress, stopping immediately.")
    
    def _handle_sigint(self, signum, frame):
        """Handle SIGINT (Ctrl+C) - graceful shutdown with option to force."""
        if self._stop_requested:
            # Second Ctrl+C - force stop
            logger.warning("Received second interrupt - forcing immediate shutdown...")
            self._force_stop = True
            raise KeyboardInterrupt("Force shutdown requested")
        else:
            logger.warning("Received SIGINT (Ctrl+C) - initiating graceful shutdown...")
            logger.info("Press Ctrl+C again to force immediate stop.")
            self._stop_requested = True
            
            if self._current_job_id:
                logger.info(f"Will stop after completing current job: {self._current_job_id}")
    
    def _handle_sigusr1(self, signum, frame):
        """Handle SIGUSR1 - check for stop file."""
        self._check_stop_file()
    
    def _check_stop_file(self) -> bool:
        """Check if stop file exists (created by stop.sh)."""
        if self._stop_file.exists():
            if not self._stop_requested:
                logger.warning("Stop file detected - initiating graceful shutdown...")
                self._stop_requested = True
            return True
        return False
    
    def start(self):
        """Called when the agent system starts - write PID file."""
        import os
        
        # Write PID file
        with open(self._pid_file, "w") as f:
            f.write(str(os.getpid()))
        
        # Clean up any leftover stop file from previous run
        if self._stop_file.exists():
            self._stop_file.unlink()
        
        logger.debug(f"Agent started with PID {os.getpid()}")
    
    def cleanup(self):
        """Clean up PID and stop files on exit."""
        try:
            if self._pid_file.exists():
                self._pid_file.unlink()
            if self._stop_file.exists():
                self._stop_file.unlink()
        except Exception as e:
            logger.debug(f"Cleanup error (non-critical): {e}")
    
    def set_current_job(self, job_id: Optional[str]):
        """Set the currently processing job ID."""
        self._current_job_id = job_id
        
        # Check stop file when job changes
        self._check_stop_file()
    
    def should_stop(self) -> bool:
        """
        Check if the agent should stop processing new jobs.
        
        This should be checked:
        - Before starting a new job
        - At the beginning of each processing loop iteration
        
        Returns:
            True if stop has been requested
        """
        # Also check the stop file
        self._check_stop_file()
        return self._stop_requested
    
    def is_force_stop(self) -> bool:
        """Check if force stop was requested."""
        return self._force_stop
    
    def register_callback(self, callback: Callable):
        """Register a callback to be called on shutdown."""
        self._on_shutdown_callbacks.append(callback)
    
    def notify_shutdown(self):
        """Call all registered shutdown callbacks."""
        for callback in self._on_shutdown_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Shutdown callback error: {e}")
    
    @property
    def stop_requested(self) -> bool:
        """Property to check if stop was requested."""
        return self._stop_requested
    
    @property
    def current_job_id(self) -> Optional[str]:
        """Get the currently processing job ID."""
        return self._current_job_id


# Global instance for easy access
def get_shutdown_manager() -> ShutdownManager:
    """Get the singleton ShutdownManager instance."""
    return ShutdownManager()
