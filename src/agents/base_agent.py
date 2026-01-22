"""
Base Agent class for the Job Application Multi-Agent System.

All agents inherit from this base class which provides common functionality.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from loguru import logger
import json
from datetime import datetime
from typing import Optional, Dict, Any


class BaseAgent(ABC):
    """Base class for all agents in the system."""
    
    def __init__(self, config: dict):
        """
        Initialize the base agent.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.jobs_dir = Path(config["paths"]["jobs_dir"])
        self.user_dir = Path(config["paths"]["user_dir"])
        self.templates_dir = Path(config["paths"]["templates_dir"])
        
        # Ensure directories exist
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.user_dir.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    def run(self) -> int:
        """
        Run the agent's main processing loop.
        
        Returns:
            Number of items processed
        """
        pass
    
    def get_job_folder(self, job_id: str) -> Path:
        """Get or create a folder for a specific job."""
        job_folder = self.jobs_dir / job_id
        job_folder.mkdir(parents=True, exist_ok=True)
        return job_folder
    
    def load_status(self, job_folder: Path) -> Dict[str, Any]:
        """Load status from a job folder."""
        status_file = job_folder / "status.json"
        if status_file.exists():
            with open(status_file, "r") as f:
                return json.load(f)
        return {}
    
    def save_status(self, job_folder: Path, status: Dict[str, Any]):
        """Save status to a job folder."""
        status["updated_at"] = datetime.utcnow().isoformat() + "Z"
        status_file = job_folder / "status.json"
        with open(status_file, "w") as f:
            json.dump(status, f, indent=2)
    
    def update_stage(self, job_folder: Path, stage: str, completed: bool = True, 
                     extra_data: Optional[Dict] = None):
        """Update a specific stage in the status."""
        status = self.load_status(job_folder)
        
        if "stages" not in status:
            status["stages"] = {}
        
        status["stages"][stage] = {
            "completed": completed,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        if extra_data:
            status["stages"][stage].update(extra_data)
        
        self.save_status(job_folder, status)
    
    def is_stage_completed(self, job_folder: Path, stage: str) -> bool:
        """Check if a stage is completed."""
        status = self.load_status(job_folder)
        return status.get("stages", {}).get(stage, {}).get("completed", False)
    
    def load_user_profile(self) -> Dict[str, Any]:
        """Load user profile from YAML file."""
        import yaml
        profile_path = Path(self.config["paths"].get("user_profile", "config/user_profile.yaml"))
        
        if not profile_path.exists():
            logger.warning(f"User profile not found at {profile_path}")
            return {}
        
        with open(profile_path, "r") as f:
            return yaml.safe_load(f)
    
    def load_user_motivations(self) -> str:
        """Load user motivations from markdown file."""
        motivations_path = self.user_dir / "motivations.md"
        
        if not motivations_path.exists():
            logger.warning(f"Motivations file not found at {motivations_path}")
            return ""
        
        with open(motivations_path, "r") as f:
            return f.read()
    
    def load_user_experience(self) -> str:
        """Load user experience from markdown file."""
        experience_path = self.user_dir / "experience.md"
        
        if not experience_path.exists():
            logger.warning(f"Experience file not found at {experience_path}")
            return ""
        
        with open(experience_path, "r") as f:
            return f.read()
    
    def save_markdown(self, job_folder: Path, filename: str, content: str):
        """Save content to a markdown file in the job folder."""
        file_path = job_folder / filename
        with open(file_path, "w") as f:
            f.write(content)
        logger.debug(f"Saved {filename} to {job_folder}")
    
    def load_markdown(self, job_folder: Path, filename: str) -> Optional[str]:
        """Load content from a markdown file in the job folder."""
        file_path = job_folder / filename
        if file_path.exists():
            with open(file_path, "r") as f:
                return f.read()
        return None
