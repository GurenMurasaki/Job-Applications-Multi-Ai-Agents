"""
Cover Letter and Gmail Draft Agent

This agent processes jobs that have customized CVs and creates:
1. Cover letters based on job requirements and user motivations
2. Gmail drafts with CV and cover letter attached
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from loguru import logger

from src.agents.base_agent import BaseAgent
from src.services.llm_service import LLMService
from src.services.latex_service import LaTeXService
from src.services.gmail_service import GmailService
from src.services.language_detector import LanguageDetector
from src.utils.shutdown_manager import get_shutdown_manager


class CoverLetterAgent(BaseAgent):
    """
    Agent that creates cover letters and Gmail drafts.
    
    Workflow:
    1. Scan jobs folder for unprocessed jobs with CVs ready
    2. Generate cover letter using LLM
    3. Compile cover letter to PDF
    4. Create Gmail draft with attachments
    """
    
    def __init__(self, config: dict):
        """Initialize the Cover Letter Agent."""
        super().__init__(config)
        
        # Initialize services
        self.llm_service = LLMService(config["llm"], agent_name="cover_letter")
        self.latex_service = LaTeXService(config["latex"])
        self.gmail_service = GmailService(config["gmail"])
        self.language_detector = LanguageDetector(config.get("language", {}))
        
        # Load templates
        self._load_email_templates()
        
        # Load user data
        self.user_profile = self.load_user_profile()
        self.user_motivations = self.load_user_motivations()
        self.user_experience = self.load_user_experience()
    
    def _load_email_templates(self):
        """Load email templates."""
        templates_file = self.templates_dir / "email_templates.json"
        if templates_file.exists():
            with open(templates_file) as f:
                self.email_templates = json.load(f)
        else:
            self.email_templates = {
                "email_en": {
                    "subject": "Application - {position} - {full_name}",
                    "body": "Dear Hiring Manager,\n\nPlease find attached my CV and cover letter.\n\nBest regards,\n{full_name}"
                },
                "email_fr": {
                    "subject": "Candidature - {position} - {full_name}",
                    "body": "Madame, Monsieur,\n\nVeuillez trouver ci-joint mon CV et ma lettre de motivation.\n\nCordialement,\n{full_name}"
                }
            }
    
    def run(self) -> int:
        """
        Main processing loop.
        
        Processes all pending jobs that have CVs ready but no drafts.
        Returns the number of jobs processed.
        
        Respects graceful shutdown requests - will finish current job
        before stopping if a stop is requested.
        """
        logger.info("Cover Letter Agent starting...")
        processed_count = 0
        shutdown_manager = get_shutdown_manager()
        
        # Get all pending jobs
        pending_jobs = self._get_pending_jobs()
        
        if not pending_jobs:
            logger.info("No pending jobs to process")
            return 0
        
        logger.info(f"Found {len(pending_jobs)} pending job(s) to process")
        
        for job_folder in pending_jobs:
            # Check for graceful shutdown before starting a new job
            if shutdown_manager.should_stop():
                logger.info("Stop requested. Will not process more jobs.")
                break
            
            try:
                # Set current job for shutdown manager
                shutdown_manager.set_current_job(job_folder.name)
                
                success = self.process_job(job_folder)
                if success:
                    processed_count += 1
                    logger.info(f"Processed job: {job_folder.name}")
                
                # Clear current job
                shutdown_manager.set_current_job(None)
                
            except Exception as e:
                logger.error(f"Failed to process job {job_folder.name}: {e}")
                shutdown_manager.set_current_job(None)
                continue
        
        if shutdown_manager.should_stop():
            logger.info(f"Agent stopped gracefully. Processed {processed_count} jobs.")
        else:
            logger.info(f"Cover Letter Agent complete. Processed {processed_count} jobs.")
        
        return processed_count
    
    def _get_pending_jobs(self) -> List[Path]:
        """Get list of job folders that need processing."""
        if not self.jobs_dir.exists():
            return []
        
        pending = []
        for job_folder in self.jobs_dir.iterdir():
            if not job_folder.is_dir():
                continue
            
            # Check if CV is ready but draft is not
            if self.is_stage_completed(job_folder, "cv_customized"):
                if not self.is_stage_completed(job_folder, "gmail_draft_created"):
                    pending.append(job_folder)
        
        return sorted(pending)
    
    def process_job(self, job_folder: Path) -> bool:
        """
        Process a single job folder.
        
        Args:
            job_folder: Path to the job folder
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Processing job: {job_folder.name}")
        
        # Load job details
        job_details = self.load_markdown(job_folder, "job_details.md")
        user_context = self.load_markdown(job_folder, "user_context.md")
        status = self.load_status(job_folder)
        
        if not job_details or not status:
            logger.error(f"Missing job details or status for {job_folder.name}")
            return False
        
        # Get language
        language = status.get("language", "en")
        
        # Step 1: Generate cover letter
        cover_letter = self._generate_cover_letter(job_folder, job_details, user_context, language)
        if not cover_letter:
            logger.error("Failed to generate cover letter")
            return False
        
        # Step 2: Save and compile cover letter
        self._save_and_compile_cover_letter(job_folder, cover_letter, language)
        self.update_stage(job_folder, "cover_letter_generated", True)
        
        # Step 3: Extract email info from job details
        email_info = self._extract_email_info(job_details, status, language)
        
        # Step 4: Create Gmail draft
        draft_id = self._create_gmail_draft(job_folder, email_info, language)
        
        if draft_id:
            self.update_stage(job_folder, "gmail_draft_created", True, {"draft_id": draft_id})
            self._save_email_draft_info(job_folder, email_info, draft_id)
            return True
        
        logger.error("Failed to create Gmail draft")
        return False
    
    def _generate_cover_letter(self, job_folder: Path, job_details: str, 
                                user_context: str, language: str) -> Optional[str]:
        """Generate cover letter using LLM."""
        logger.info(f"Generating cover letter in {language}...")
        
        # Load template
        template_name = f"cover_letter_{language}.tex"
        template_path = self.templates_dir / template_name
        
        if not template_path.exists():
            logger.warning(f"Template {template_name} not found, using cover_letter_en.tex")
            template_path = self.templates_dir / "cover_letter_en.tex"
        
        with open(template_path, "r") as f:
            template = f.read()
        
        # Create prompt
        prompt = self._create_cover_letter_prompt(template, job_details, user_context, language)
        
        try:
            cover_letter = self.llm_service.generate(prompt)
            return cover_letter
        except Exception as e:
            logger.error(f"LLM failed to generate cover letter: {e}")
            return None
    
    def _create_cover_letter_prompt(self, template: str, job_details: str, 
                                     user_context: str, language: str) -> str:
        """Create prompt for cover letter generation."""
        personal = self.user_profile.get("personal", {})
        
        lang_instruction = "French (formal business French)" if language == "fr" else "English (professional business English)"
        
        return f"""You are an expert cover letter writer. Create a compelling cover letter for this job application.

## User Profile
Name: {personal.get('first_name', '')} {personal.get('last_name', '')}
Email: {personal.get('email', '')}
Phone: {personal.get('phone', '')}
Address: {personal.get('address', '')}

## User Motivations
{self.user_motivations}

## User Experience
{self.user_experience}

## Job Details
{job_details}

## User Context for This Job
{user_context}

## Cover Letter Template (LaTeX)
{template}

## Instructions
1. Replace all <<PLACEHOLDER>> markers with appropriate content
2. Write a compelling opening paragraph that shows genuine interest
3. Highlight relevant experience and skills that match the job
4. Show enthusiasm and motivation for the role
5. Keep the tone professional but personable
6. Language: {lang_instruction}
7. Keep the LaTeX syntax valid and compilable
8. Date should be: {datetime.now().strftime("%B %d, %Y")}

Return ONLY the complete LaTeX document, ready to compile. No explanations.
"""
    
    def _save_and_compile_cover_letter(self, job_folder: Path, content: str, language: str):
        """Save cover letter and compile to PDF."""
        # Save LaTeX file
        tex_file = job_folder / "cover_letter.tex"
        with open(tex_file, "w") as f:
            f.write(content)
        logger.info(f"Saved cover letter LaTeX to {tex_file}")
        
        # Compile to PDF
        try:
            pdf_path = self.latex_service.compile(tex_file)
            if pdf_path:
                logger.info(f"Compiled cover letter PDF: {pdf_path}")
            else:
                logger.warning("PDF compilation returned no path")
        except Exception as e:
            logger.error(f"Failed to compile cover letter to PDF: {e}")
    
    def _extract_email_info(self, job_details: str, status: dict, language: str) -> Dict[str, Any]:
        """Extract email information from job details."""
        # Parse job details for contact info
        lines = job_details.split("\n")
        
        info = {
            "recipient_email": "",
            "company": "",
            "position": "",
            "language": language
        }
        
        for line in lines:
            if "**Title**:" in line:
                info["position"] = line.split("**Title**:")[-1].strip()
            elif "**Company**:" in line:
                info["company"] = line.split("**Company**:")[-1].strip()
            elif "**Email**:" in line:
                email = line.split("**Email**:")[-1].strip()
                if email and email != "Not specified":
                    info["recipient_email"] = email
        
        return info
    
    def _create_gmail_draft(self, job_folder: Path, email_info: Dict[str, Any], 
                            language: str) -> Optional[str]:
        """Create Gmail draft with CV and cover letter attached."""
        personal = self.user_profile.get("personal", {})
        full_name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
        
        # Get email template
        template_key = f"email_{language}"
        template = self.email_templates.get(template_key, self.email_templates.get("email_en", {}))
        
        # Format email content
        subject = template.get("subject", "Application - {position} - {full_name}").format(
            position=email_info.get("position", "Position"),
            full_name=full_name,
            company=email_info.get("company", "Company")
        )
        
        body = template.get("body", "").format(
            position=email_info.get("position", "Position"),
            full_name=full_name,
            company=email_info.get("company", "Company"),
            email=personal.get("email", ""),
            phone=personal.get("phone", "")
        )
        
        # Collect attachments
        attachments = []
        
        cv_pdf = job_folder / "cv_customized.pdf"
        if cv_pdf.exists():
            attachments.append({
                "path": str(cv_pdf),
                "filename": f"CV_{full_name.replace(' ', '_')}.pdf"
            })
        
        cover_letter_pdf = job_folder / "cover_letter.pdf"
        if cover_letter_pdf.exists():
            letter_name = "Lettre_Motivation" if language == "fr" else "Cover_Letter"
            attachments.append({
                "path": str(cover_letter_pdf),
                "filename": f"{letter_name}_{full_name.replace(' ', '_')}.pdf"
            })
        
        # Create draft
        try:
            draft_id = self.gmail_service.create_draft(
                to=email_info.get("recipient_email", ""),
                subject=subject,
                body=body,
                attachments=attachments
            )
            return draft_id
        except Exception as e:
            logger.error(f"Failed to create Gmail draft: {e}")
            return None
    
    def _save_email_draft_info(self, job_folder: Path, email_info: Dict[str, Any], draft_id: str):
        """Save email draft information to file."""
        draft_info = {
            "draft_id": draft_id,
            "to": email_info.get("recipient_email", ""),
            "company": email_info.get("company", ""),
            "position": email_info.get("position", ""),
            "language": email_info.get("language", "en"),
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        
        draft_file = job_folder / "email_draft.json"
        with open(draft_file, "w") as f:
            json.dump(draft_info, f, indent=2)
        logger.info(f"Saved email draft info to {draft_file}")
