"""
Main entry point for the Job Application Multi-Agent System.

This module orchestrates the sequential execution of agents:
1. CV Customizer Agent - Consumes Kafka messages and creates customized CVs
2. Cover Letter Agent - Creates cover letters and Gmail drafts

Additionally, there's a standalone agent:
- Profile Updater Agent - Updates user profile from a CV file (runs independently)

Signal Handling:
- SIGTERM: Graceful shutdown (finish current job, then stop)
- SIGINT (Ctrl+C): Graceful shutdown (second Ctrl+C forces immediate stop)
- Stop file (.stop_requested): Created by stop.sh for graceful shutdown
"""

import click
import sys
import atexit
from pathlib import Path
from loguru import logger

from src.utils.config import load_config
from src.utils.logger import setup_logger
from src.utils.shutdown_manager import get_shutdown_manager
from src.agents.cv_customizer_agent import CVCustomizerAgent
from src.agents.cover_letter_agent import CoverLetterAgent
from src.agents.profile_updater_agent import ProfileUpdaterAgent


def run_cv_customizer(config: dict) -> tuple[bool, bool]:
    """
    Run the CV Customizer Agent.
    
    Consumes all messages from Kafka and creates customized CVs.
    
    Returns:
        Tuple of (success, was_stopped): success indicates if processing worked,
        was_stopped indicates if a stop was requested during processing.
    """
    shutdown_manager = get_shutdown_manager()
    
    if shutdown_manager.should_stop():
        logger.info("Stop requested before starting CV Customizer Agent.")
        return True, True
    
    logger.info("Starting CV Customizer Agent...")
    agent = CVCustomizerAgent(config)
    
    try:
        processed_count = agent.run()
        was_stopped = shutdown_manager.should_stop()
        
        if was_stopped:
            logger.info(f"CV Customizer Agent stopped after processing {processed_count} jobs.")
        else:
            logger.info(f"CV Customizer Agent completed. Processed {processed_count} jobs.")
        
        return True, was_stopped
    except KeyboardInterrupt:
        logger.warning("CV Customizer Agent interrupted.")
        return True, True
    except Exception as e:
        logger.error(f"CV Customizer Agent failed: {e}")
        return False, False


def run_cover_letter_agent(config: dict) -> tuple[bool, bool]:
    """
    Run the Cover Letter & Gmail Draft Agent.
    
    Processes all pending job folders and creates cover letters + drafts.
    
    Returns:
        Tuple of (success, was_stopped): success indicates if processing worked,
        was_stopped indicates if a stop was requested during processing.
    """
    shutdown_manager = get_shutdown_manager()
    
    if shutdown_manager.should_stop():
        logger.info("Stop requested before starting Cover Letter Agent.")
        return True, True
    
    logger.info("Starting Cover Letter & Gmail Draft Agent...")
    agent = CoverLetterAgent(config)
    
    try:
        processed_count = agent.run()
        was_stopped = shutdown_manager.should_stop()
        
        if was_stopped:
            logger.info(f"Cover Letter Agent stopped after processing {processed_count} jobs.")
        else:
            logger.info(f"Cover Letter Agent completed. Processed {processed_count} jobs.")
        
        return True, was_stopped
    except KeyboardInterrupt:
        logger.warning("Cover Letter Agent interrupted.")
        return True, True
    except Exception as e:
        logger.error(f"Cover Letter Agent failed: {e}")
        return False, False


def run_profile_updater(config: dict, cv_path: str = None, **kwargs) -> bool:
    """
    Run the Profile Updater Agent.
    
    Supports multiple update modes:
    - cv_path: Update from any CV file (PDF, DOCX, TXT, MD, TEX)
    - cv_en/cv_fr: Initial setup with LaTeX CV templates
    - letter_en/letter_fr: Provide motivation letter examples
    - add_text: Incremental update via text command
    """
    logger.info("Starting Profile Updater Agent...")
    agent = ProfileUpdaterAgent(config)
    
    try:
        success = agent.run(cv_path, **kwargs)
        if success:
            logger.info("Profile Updater Agent completed successfully.")
        else:
            logger.error("Profile Updater Agent failed.")
        return success == 1
    except Exception as e:
        logger.error(f"Profile Updater Agent failed: {e}")
        return False


def show_status(config: dict):
    """Display status of all jobs."""
    jobs_dir = Path(config["paths"]["jobs_dir"])
    
    if not jobs_dir.exists():
        logger.info("No jobs directory found.")
        return
    
    jobs = list(jobs_dir.iterdir())
    if not jobs:
        logger.info("No jobs found.")
        return
    
    logger.info(f"Found {len(jobs)} job(s):")
    
    import json
    for job_folder in sorted(jobs):
        if job_folder.is_dir():
            status_file = job_folder / "status.json"
            if status_file.exists():
                with open(status_file) as f:
                    status = json.load(f)
                
                cv_ready = status.get("stages", {}).get("cv_customized", {}).get("completed", False)
                letter_ready = status.get("stages", {}).get("cover_letter_generated", {}).get("completed", False)
                draft_ready = status.get("stages", {}).get("gmail_draft_created", {}).get("completed", False)
                
                status_icons = {
                    "cv": "✅" if cv_ready else "❌",
                    "letter": "✅" if letter_ready else "❌",
                    "draft": "✅" if draft_ready else "❌"
                }
                
                logger.info(
                    f"  {job_folder.name}: CV {status_icons['cv']} | "
                    f"Letter {status_icons['letter']} | "
                    f"Draft {status_icons['draft']}"
                )
            else:
                logger.info(f"  {job_folder.name}: No status file")


@click.command()
@click.option("--agent", type=click.Choice(["cv", "cover-letter", "all"]), default="all",
              help="Which agent to run")
@click.option("--status", "show_status_flag", is_flag=True, help="Show status of all jobs")
@click.option("--update-profile", "update_profile_flag", is_flag=True, 
              help="Update profile from CV (runs independently)")
@click.option("--cv-file", default=None, help="Path to CV file for profile update")
@click.option("--cv-en", default=None, help="Path to English LaTeX CV (base template)")
@click.option("--cv-fr", default=None, help="Path to French LaTeX CV (base template)")
@click.option("--letter-en", default=None, help="Path to English motivation letter example")
@click.option("--letter-fr", default=None, help="Path to French motivation letter example")
@click.option("--add-text", default=None, help="Text describing what to add incrementally")
@click.option("--config-file", default="config/config.yaml", help="Path to config file")
@click.option("--debug", is_flag=True, help="Enable debug logging")
def main(agent: str, show_status_flag: bool, update_profile_flag: bool, 
         cv_file: str, cv_en: str, cv_fr: str, letter_en: str, letter_fr: str,
         add_text: str, config_file: str, debug: bool):
    """
    Job Application Multi-Agent System
    
    Sequential execution of agents for automated job application processing.
    
    \b
    Examples:
      python -m src.main                          # Run full pipeline
      python -m src.main --agent cv               # Run only CV agent
      python -m src.main --agent cover-letter     # Run only cover letter agent
      python -m src.main --update-profile --cv-file my_cv.pdf  # Update profile from CV
      python -m src.main --update-profile --cv-en cv_en.tex --cv-fr cv_fr.tex  # Initial setup
      python -m src.main --update-profile --add-text "Add AWS certification 2026"
      python -m src.main --status                 # Show job statuses
    
    \b
    Stopping:
      ./stop.sh                                   # Graceful stop (finish current job)
      ./stop.sh --force                           # Force stop immediately
      Ctrl+C                                      # Graceful stop (Ctrl+C again to force)
    """
    # Initialize shutdown manager
    shutdown_manager = get_shutdown_manager()
    shutdown_manager.start()
    atexit.register(shutdown_manager.cleanup)
    
    # Setup logging
    log_level = "DEBUG" if debug else "INFO"
    setup_logger(log_level)
    
    logger.info("=" * 60)
    logger.info("Job Application Multi-Agent System")
    logger.info("=" * 60)
    
    # Load configuration
    try:
        config = load_config(config_file)
        logger.info(f"Configuration loaded from {config_file}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    # Handle profile update (independent agent)
    if update_profile_flag or cv_en or cv_fr or letter_en or letter_fr or add_text:
        logger.info("Running Profile Updater (independent mode)...")
        success = run_profile_updater(
            config, 
            cv_path=cv_file,
            cv_en=cv_en,
            cv_fr=cv_fr,
            letter_en=letter_en,
            letter_fr=letter_fr,
            add_text=add_text
        )
        sys.exit(0 if success else 1)
    
    # Show status if requested
    if show_status_flag:
        show_status(config)
        return
    
    # Run agents based on selection
    if agent == "cv":
        success, was_stopped = run_cv_customizer(config)
        if was_stopped:
            logger.info("Agent stopped gracefully.")
        sys.exit(0 if success else 1)
    
    elif agent == "cover-letter":
        success, was_stopped = run_cover_letter_agent(config)
        if was_stopped:
            logger.info("Agent stopped gracefully.")
        sys.exit(0 if success else 1)
    
    elif agent == "all":
        # Sequential execution: CV first, then Cover Letter
        logger.info("Running full pipeline (sequential)...")
        
        # Step 1: CV Customizer
        cv_success, cv_stopped = run_cv_customizer(config)
        if not cv_success:
            logger.error("CV Customizer failed. Stopping pipeline.")
            sys.exit(1)
        
        if cv_stopped:
            logger.info("Pipeline stopped gracefully after CV Customizer.")
            logger.info("Run again to continue with Cover Letter Agent.")
            sys.exit(0)
        
        # Step 2: Cover Letter & Gmail Draft
        letter_success, letter_stopped = run_cover_letter_agent(config)
        if not letter_success:
            logger.error("Cover Letter Agent failed.")
            sys.exit(1)
        
        if letter_stopped:
            logger.info("=" * 60)
            logger.info("Pipeline stopped gracefully.")
            logger.info("Some jobs may still need cover letters. Run again to continue.")
            logger.info("=" * 60)
        else:
            logger.info("=" * 60)
            logger.info("Pipeline completed successfully!")
            logger.info("Check your Gmail drafts for ready-to-send applications.")
            logger.info("=" * 60)


if __name__ == "__main__":
    main()
