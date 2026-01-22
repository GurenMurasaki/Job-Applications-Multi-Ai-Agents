"""
CV Customizer Agent

This agent consumes job offers from Kafka and creates customized CVs.
It handles various job data schemas from different platforms (LinkedIn, Indeed, etc.)
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from loguru import logger

from src.agents.base_agent import BaseAgent
from src.consumers.kafka_consumer import JobKafkaConsumer
from src.services.llm_service import LLMService
from src.services.latex_service import LaTeXService
from src.services.language_detector import LanguageDetector
from src.models.job_offer import NormalizedJobOffer, normalize_job_data
from src.utils.shutdown_manager import get_shutdown_manager


class CVCustomizerAgent(BaseAgent):
    """
    Agent that consumes Kafka messages and creates customized CVs.
    
    Workflow:
    1. Consume job data from Kafka
    2. Normalize job schema (handle LinkedIn, Indeed, etc.)
    3. Create job folder with details
    4. Use LLM to customize CV based on job requirements
    5. Compile LaTeX to PDF
    """
    
    def __init__(self, config: dict):
        """Initialize the CV Customizer Agent."""
        super().__init__(config)
        
        # Initialize services
        self.kafka_consumer = JobKafkaConsumer(config["kafka"])
        self.llm_service = LLMService(config["llm"], agent_name="cv_customizer")
        self.latex_service = LaTeXService(config["latex"])
        self.language_detector = LanguageDetector(config.get("language", {}))
        
        # Load user data
        self.user_profile = self.load_user_profile()
        self.user_motivations = self.load_user_motivations()
        self.user_experience = self.load_user_experience()
    
    def run(self) -> int:
        """
        Main processing loop.
        
        Consumes all available Kafka messages and processes each job.
        Returns the number of jobs processed.
        
        Respects graceful shutdown requests - will finish current job
        before stopping if a stop is requested.
        """
        logger.info("CV Customizer Agent starting...")
        processed_count = 0
        shutdown_manager = get_shutdown_manager()
        
        try:
            # Consume messages until timeout (no more messages) or stop requested
            for raw_message in self.kafka_consumer.consume():
                # Check for graceful shutdown before starting a new job
                if shutdown_manager.should_stop():
                    logger.info("Stop requested. Will not process more jobs.")
                    break
                
                try:
                    # Set current job for shutdown manager
                    job_id = raw_message.get("job_id") or raw_message.get("id", "unknown")
                    shutdown_manager.set_current_job(job_id)
                    
                    job = self.process_message(raw_message)
                    if job:
                        processed_count += 1
                        logger.info(f"Processed job {processed_count}: {job.title} at {job.company}")
                    
                    # Clear current job
                    shutdown_manager.set_current_job(None)
                    
                except Exception as e:
                    logger.error(f"Failed to process message: {e}")
                    shutdown_manager.set_current_job(None)
                    continue
            
            if shutdown_manager.should_stop():
                logger.info(f"Agent stopped gracefully. Processed {processed_count} jobs.")
            else:
                logger.info(f"Kafka consumption complete. Total jobs processed: {processed_count}")
            
        finally:
            self.kafka_consumer.close()
        
        return processed_count
    
    def process_message(self, raw_message: Dict[str, Any]) -> Optional[NormalizedJobOffer]:
        """
        Process a single Kafka message.
        
        Args:
            raw_message: Raw job data from Kafka
            
        Returns:
            Normalized job offer if successful, None otherwise
        """
        # Step 1: Normalize the job data
        job = normalize_job_data(raw_message)
        if not job:
            logger.warning("Failed to normalize job data")
            return None
        
        logger.info(f"Processing job: {job.title} at {job.company} ({job.source})")
        
        # Step 2: Create job folder
        job_folder = self.get_job_folder(job.job_id)
        
        # Step 3: Detect language
        job.language = self.language_detector.detect_job_language(job)
        logger.info(f"Detected language: {job.language}")
        
        # Step 4: Save raw job data
        self._save_raw_data(job_folder, raw_message)
        
        # Step 5: Create job_details.md
        self._create_job_details(job_folder, job)
        
        # Step 6: Create user_context.md
        self._create_user_context(job_folder, job)
        
        # Step 7: Initialize status
        self._initialize_status(job_folder, job)
        self.update_stage(job_folder, "kafka_consumed", True)
        
        # Step 8: Customize CV using LLM
        cv_content = self._customize_cv(job_folder, job)
        if not cv_content:
            logger.error(f"Failed to customize CV for job {job.job_id}")
            return None
        
        # Step 9: Save and compile CV
        self._save_and_compile_cv(job_folder, job, cv_content)
        self.update_stage(job_folder, "cv_customized", True)
        
        return job
    
    def _save_raw_data(self, job_folder: Path, raw_message: Dict[str, Any]):
        """Save raw Kafka message to job folder."""
        raw_file = job_folder / "raw_job_data.json"
        with open(raw_file, "w") as f:
            json.dump(raw_message, f, indent=2, default=str)
    
    def _create_job_details(self, job_folder: Path, job: NormalizedJobOffer):
        """Create job_details.md with structured job information."""
        requirements_list = "\n".join(f"- {req}" for req in job.requirements) if job.requirements else "- Not specified"
        
        content = f"""# Job Details

## Position
**Title**: {job.title}
**Company**: {job.company}
**Location**: {job.location}
**Country**: {job.country or "Not specified"}

## Description
{job.description}

## Requirements
{requirements_list}

## Contact
**Email**: {job.contact_email or "Not specified"}
**Apply URL**: {job.apply_url or "Not specified"}

## Metadata
- **Source**: {job.source}
- **Job ID**: {job.job_id}
- **Extracted**: {job.extracted_at}
- **Language**: {job.language}
"""
        self.save_markdown(job_folder, "job_details.md", content)
    
    def _create_user_context(self, job_folder: Path, job: NormalizedJobOffer):
        """Create user_context.md with relevant user info for this job."""
        # Match skills
        matched_skills = self._match_skills(job.requirements)
        skills_section = self._format_matched_skills(matched_skills, job.requirements)
        
        # Get relevant experience
        relevant_exp = self._get_relevant_experience(job)
        
        # Language selection reasoning
        lang_reason = self._get_language_reasoning(job)
        
        content = f"""# User Context for This Application

## Matching Skills
{skills_section}

## Relevant Experience
{relevant_exp}

## Key Motivations
{self._extract_key_motivations(job)}

## Language Selection
- **CV Language**: {job.language.upper()}
- **Cover Letter Language**: {job.language.upper()}
- **Email Language**: {job.language.upper()}
- **Reason**: {lang_reason}

## User Profile Summary
{self._get_profile_summary()}
"""
        self.save_markdown(job_folder, "user_context.md", content)
    
    def _match_skills(self, requirements: List[str]) -> Dict[str, bool]:
        """Match job requirements with user skills."""
        if not requirements:
            return {}
        
        user_skills = set()
        
        # Primary skills
        primary = self.user_profile.get("professional", {}).get("primary_skills", [])
        user_skills.update(s.lower() for s in primary)
        
        # Secondary skills
        secondary = self.user_profile.get("professional", {}).get("secondary_skills", [])
        user_skills.update(s.lower() for s in secondary)
        
        matched = {}
        for req in requirements:
            req_lower = req.lower()
            matched[req] = any(skill in req_lower or req_lower in skill for skill in user_skills)
        
        return matched
    
    def _format_matched_skills(self, matched: Dict[str, bool], requirements: List[str]) -> str:
        """Format matched skills for display."""
        if not matched:
            return "- Skills matching not available"
        
        lines = []
        for skill, is_matched in matched.items():
            icon = "✓" if is_matched else "○"
            lines.append(f"- {skill} {icon}")
        
        return "\n".join(lines) if lines else "- No requirements specified"
    
    def _get_relevant_experience(self, job: NormalizedJobOffer) -> str:
        """Extract relevant experience for the job."""
        experience = self.user_profile.get("experience", [])
        if not experience:
            return "See experience.md for full details"
        
        lines = []
        for exp in experience[:2]:  # Top 2 experiences
            title = exp.get("title", "")
            company = exp.get("company", "")
            highlights = exp.get("highlights", [])[:2]  # Top 2 highlights
            
            lines.append(f"- **{title}** at {company}")
            for h in highlights:
                lines.append(f"  - {h}")
        
        return "\n".join(lines) if lines else "See experience.md for full details"
    
    def _get_language_reasoning(self, job: NormalizedJobOffer) -> str:
        """Get reasoning for language selection."""
        if job.country and job.country.lower() == "france":
            if "english" in job.description.lower():
                return "Job is in France but requires English proficiency"
            return "Job is in France, using French by default"
        return f"Based on job location: {job.location}"
    
    def _extract_key_motivations(self, job: NormalizedJobOffer) -> str:
        """Extract key motivations relevant to this job."""
        return f"- Interest in {job.company}'s mission\n- Opportunity for growth in {job.location}"
    
    def _get_profile_summary(self) -> str:
        """Get user profile summary."""
        personal = self.user_profile.get("personal", {})
        professional = self.user_profile.get("professional", {})
        
        name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
        title = professional.get("current_title", "Professional")
        years = professional.get("years_experience", 0)
        
        return f"**{name}** - {title} with {years} years of experience"
    
    def _initialize_status(self, job_folder: Path, job: NormalizedJobOffer):
        """Initialize status.json for the job."""
        status = {
            "job_id": job.job_id,
            "source": job.source,
            "language": job.language,
            "stages": {},
            "processed": False,
            "errors": [],
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        self.save_status(job_folder, status)
    
    def _customize_cv(self, job_folder: Path, job: NormalizedJobOffer) -> Optional[str]:
        """Use LLM to customize CV based on job requirements."""
        logger.info(f"Customizing CV for {job.title} at {job.company}...")
        
        # Load template
        template_name = f"cv_{job.language}.tex"
        template_path = self.templates_dir / template_name
        
        if not template_path.exists():
            logger.warning(f"Template {template_name} not found, using cv_en.tex")
            template_path = self.templates_dir / "cv_en.tex"
        
        with open(template_path, "r") as f:
            template = f.read()
        
        # Load job details and user context
        job_details = self.load_markdown(job_folder, "job_details.md")
        user_context = self.load_markdown(job_folder, "user_context.md")
        
        # Create prompt for LLM
        prompt = self._create_cv_customization_prompt(
            template, job_details, user_context, job
        )
        
        # Call LLM
        try:
            customized_cv = self.llm_service.generate(prompt)
            return customized_cv
        except Exception as e:
            logger.error(f"LLM failed to customize CV: {e}")
            return None
    
    def _create_cv_customization_prompt(self, template: str, job_details: str, 
                                         user_context: str, job: NormalizedJobOffer) -> str:
        """Create prompt for CV customization."""
        personal = self.user_profile.get("personal", {})
        professional = self.user_profile.get("professional", {})
        
        return f"""You are an expert CV writer. Customize this CV template for the specific job offer.

## User Profile
Name: {personal.get('first_name', '')} {personal.get('last_name', '')}
Email: {personal.get('email', '')}
Phone: {personal.get('phone', '')}
Location: {personal.get('address', '')}
LinkedIn: {personal.get('linkedin', '')}
GitHub: {personal.get('github', '')}
Current Title: {professional.get('current_title', '')}

## User Experience
{self.user_experience}

## Job Details
{job_details}

## User Context for This Job
{user_context}

## CV Template (LaTeX)
{template}

## Instructions
1. Replace all <<PLACEHOLDER>> markers with appropriate content
2. Tailor the professional summary to match the job requirements
3. Highlight skills that match the job requirements
4. Order experience and skills to emphasize relevance to this job
5. Keep the LaTeX syntax valid and compilable
6. Language: {job.language.upper()}

Return ONLY the complete LaTeX document, ready to compile. No explanations.
"""
    
    def _save_and_compile_cv(self, job_folder: Path, job: NormalizedJobOffer, cv_content: str):
        """Save CV content and compile to PDF."""
        # Save LaTeX file
        tex_file = job_folder / "cv_customized.tex"
        with open(tex_file, "w") as f:
            f.write(cv_content)
        logger.info(f"Saved customized CV LaTeX to {tex_file}")
        
        # Compile to PDF
        try:
            pdf_path = self.latex_service.compile(tex_file)
            if pdf_path:
                logger.info(f"Compiled CV PDF: {pdf_path}")
            else:
                logger.warning("PDF compilation returned no path")
        except Exception as e:
            logger.error(f"Failed to compile CV to PDF: {e}")
