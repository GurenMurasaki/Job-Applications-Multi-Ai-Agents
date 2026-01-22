"""
Profile Updater Agent (Enhanced)

This agent manages user profile updates from various sources:
- LaTeX CV files (English and French) - used as base templates
- Motivation letter examples (English and French)
- Incremental text updates (add new certifications, experience, etc.)
- Other CV formats (PDF, DOCX, TXT, MD)

Runs independently from the main job application flow.
"""

import json
import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger
import yaml

from src.agents.base_agent import BaseAgent
from src.services.llm_service import LLMService
from src.services.cv_parser_service import CVParserService
from src.services.language_detector import LanguageDetector


class ProfileUpdaterAgent(BaseAgent):
    """
    Enhanced agent that updates user profile from various sources.
    
    Supports:
    - Initial setup from LaTeX CVs (English + French)
    - Initial setup from motivation letter examples
    - Incremental updates via text commands
    - Full CV replacement from any format
    """
    
    def __init__(self, config: dict):
        """Initialize the Profile Updater Agent."""
        super().__init__(config)
        
        # Initialize services
        self.llm_service = LLMService(config["llm"], agent_name="profile_updater")
        self.cv_parser = CVParserService()
        self.language_detector = LanguageDetector(config.get("language", {}))
        
        # Paths
        self.profile_path = Path(config["paths"].get("user_profile", "config/user_profile.yaml"))
        self.backups_dir = Path("data/backups")
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        
        # User base templates storage
        self.user_templates_dir = Path("data/user/templates")
        self.user_templates_dir.mkdir(parents=True, exist_ok=True)
    
    def run(self, cv_path: Optional[str] = None, **kwargs) -> int:
        """
        Main entry point - routes to appropriate update method.
        
        Args:
            cv_path: Path to CV file (optional)
            **kwargs:
                - cv_en: Path to English LaTeX CV (base template)
                - cv_fr: Path to French LaTeX CV (base template)
                - letter_en: Path to English motivation letter example
                - letter_fr: Path to French motivation letter example
                - add_text: Text describing what to add incrementally
                - update_type: "initial", "add", "replace", or "auto"
            
        Returns:
            1 if successful, 0 if failed
        """
        logger.info("Profile Updater Agent starting...")
        
        # Determine update type
        update_type = kwargs.get("update_type", "auto")
        
        if update_type == "initial" or (kwargs.get("cv_en") or kwargs.get("cv_fr")):
            # Initial setup with LaTeX templates
            return self._initial_setup(
                cv_en=kwargs.get("cv_en"),
                cv_fr=kwargs.get("cv_fr"),
                letter_en=kwargs.get("letter_en"),
                letter_fr=kwargs.get("letter_fr")
            )
        
        elif update_type == "add" or kwargs.get("add_text"):
            # Incremental update via text
            return self._incremental_update(kwargs.get("add_text", ""))
        
        elif cv_path:
            # Full CV replacement/update
            return self._full_cv_update(cv_path)
        
        else:
            # Try to find CV in uploads
            cv_path = self._find_cv_in_uploads()
            if cv_path:
                return self._full_cv_update(cv_path)
            
            logger.error("No input provided. Use --cv-file, --cv-en, --cv-fr, or --add-text")
            return 0
    
    # =========================================================================
    # Initial Setup (LaTeX CVs + Motivation Letters)
    # =========================================================================
    
    def _initial_setup(self, cv_en: str = None, cv_fr: str = None,
                       letter_en: str = None, letter_fr: str = None) -> int:
        """
        Initial setup from LaTeX CVs and motivation letters.
        
        This extracts your info and stores your templates as base.
        """
        logger.info("=" * 60)
        logger.info("  INITIAL PROFILE SETUP")
        logger.info("=" * 60)
        
        extracted_data = {
            "cv_en": None,
            "cv_fr": None,
            "letter_en": None,
            "letter_fr": None
        }
        
        # Process English CV
        if cv_en:
            logger.info(f"Processing English CV: {cv_en}")
            extracted_data["cv_en"] = self._process_latex_cv(cv_en, "en")
            self._save_user_template(cv_en, "cv_base_en.tex")
        
        # Process French CV
        if cv_fr:
            logger.info(f"Processing French CV: {cv_fr}")
            extracted_data["cv_fr"] = self._process_latex_cv(cv_fr, "fr")
            self._save_user_template(cv_fr, "cv_base_fr.tex")
        
        # Process English motivation letter
        if letter_en:
            logger.info(f"Processing English motivation letter: {letter_en}")
            extracted_data["letter_en"] = self._process_motivation_letter(letter_en, "en")
            self._save_user_template(letter_en, "letter_base_en.tex")
        
        # Process French motivation letter
        if letter_fr:
            logger.info(f"Processing French motivation letter: {letter_fr}")
            extracted_data["letter_fr"] = self._process_motivation_letter(letter_fr, "fr")
            self._save_user_template(letter_fr, "letter_base_fr.tex")
        
        # Merge extracted data from all sources
        merged_data = self._merge_extracted_data(extracted_data)
        
        if not merged_data:
            logger.error("Failed to extract any data from provided files")
            return 0
        
        # Backup current files and update all
        self._backup_current_files()
        self._update_all_files(merged_data, extracted_data)
        
        logger.info("=" * 60)
        logger.info("  ✅ Initial setup complete!")
        logger.info("=" * 60)
        
        return 1
    
    def _process_latex_cv(self, file_path: str, language: str) -> Optional[Dict]:
        """Process a LaTeX CV file and extract profile data."""
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return None
        
        raw_content, text, structure = self.cv_parser.extract_latex_with_structure(path)
        
        if not text:
            logger.error(f"Failed to extract text from {file_path}")
            return None
        
        logger.info(f"  - Extracted {len(text)} chars, detected lang: {structure.get('language', 'unknown')}")
        
        # Extract profile data using LLM
        profile_data = self._extract_profile_data(text, language)
        
        if profile_data:
            # Store LaTeX structure for later use
            profile_data["_latex_structure"] = structure
            profile_data["_raw_latex"] = raw_content
        
        return profile_data
    
    def _process_motivation_letter(self, file_path: str, language: str) -> Optional[Dict]:
        """Process a motivation letter file and extract style info."""
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return None
        
        if path.suffix.lower() == ".tex":
            raw_content, text, structure = self.cv_parser.extract_latex_with_structure(path)
        else:
            text = self.cv_parser.extract_text(path)
            raw_content = text
            structure = {}
        
        if not text:
            logger.error(f"Failed to extract from {file_path}")
            return None
        
        # Extract letter style and key phrases
        letter_data = self._extract_letter_style(text, raw_content, language)
        letter_data["_raw_content"] = raw_content
        letter_data["_structure"] = structure
        
        return letter_data
    
    def _extract_letter_style(self, text: str, raw_content: str, language: str) -> Dict:
        """Extract motivation letter style and key elements using LLM."""
        prompt = f"""Analyze this motivation letter and extract writing style elements.

## Motivation Letter ({language.upper()})
{text[:4000]}

## Extract as JSON:
{{
  "opening_style": "How the letter opens (greeting, first paragraph tone)",
  "closing_style": "How the letter closes (sign-off style)",
  "tone": "Overall tone (Professional/Formal/Friendly/Enthusiastic/etc)",
  "key_phrases": ["Reusable phrases from the letter"],
  "structure": ["List of paragraph types: greeting, intro, experience, skills, closing, signature"],
  "strengths_highlighted": ["What personal strengths are emphasized"],
  "language": "{language}"
}}

Return ONLY valid JSON:"""
        
        try:
            response = self.llm_service.generate(prompt)
            result = self._parse_json_response(response)
            return result if result else {}
        except Exception as e:
            logger.error(f"Letter style extraction failed: {e}")
            return {}
    
    def _save_user_template(self, source_path: str, dest_name: str):
        """Save a user's template file as base for future reference."""
        source = Path(source_path)
        dest = self.user_templates_dir / dest_name
        
        try:
            shutil.copy2(source, dest)
            logger.info(f"  - Saved as base template: {dest_name}")
        except Exception as e:
            logger.error(f"Failed to save template: {e}")
    
    def _merge_extracted_data(self, extracted: Dict) -> Optional[Dict]:
        """Merge data extracted from multiple CV/letter sources."""
        merged = {
            "personal": {},
            "professional": {},
            "experience": [],
            "education": [],
            "summary": "",
            "interests": []
        }
        
        # Priority: English CV first, then French CV
        for key in ["cv_en", "cv_fr"]:
            data = extracted.get(key)
            if not data:
                continue
            
            # Merge personal info (first non-empty wins)
            for field, value in data.get("personal", {}).items():
                if value and not merged["personal"].get(field):
                    merged["personal"][field] = value
            
            # Merge professional info
            for field, value in data.get("professional", {}).items():
                if field in ["primary_skills", "secondary_skills", "certifications", "languages"]:
                    # Combine lists
                    existing = merged["professional"].get(field, [])
                    if isinstance(value, list):
                        # Deduplicate
                        existing_set = set(str(x) for x in existing)
                        for item in value:
                            if str(item) not in existing_set:
                                existing.append(item)
                                existing_set.add(str(item))
                        merged["professional"][field] = existing
                elif value and not merged["professional"].get(field):
                    merged["professional"][field] = value
            
            # Merge experience (dedupe by company+title)
            existing_exp = {(e.get("company"), e.get("title")) for e in merged["experience"]}
            for exp in data.get("experience", []):
                key_tuple = (exp.get("company"), exp.get("title"))
                if key_tuple not in existing_exp:
                    merged["experience"].append(exp)
                    existing_exp.add(key_tuple)
            
            # Merge education (dedupe by institution)
            existing_edu = {e.get("institution") for e in merged["education"]}
            for edu in data.get("education", []):
                if edu.get("institution") not in existing_edu:
                    merged["education"].append(edu)
                    existing_edu.add(edu.get("institution"))
            
            # Summary and interests
            if data.get("summary") and not merged["summary"]:
                merged["summary"] = data["summary"]
            if data.get("interests"):
                merged["interests"] = list(set(merged["interests"] + data["interests"]))
        
        # Check we have minimum data
        if merged["personal"].get("first_name") or merged["professional"].get("primary_skills"):
            return merged
        
        return None
    
    def _update_all_files(self, merged_data: Dict, extracted: Dict):
        """Update all profile files from merged data."""
        # Update profile YAML
        self._update_profile_yaml(merged_data)
        
        # Determine primary language (prefer English)
        lang = "en" if extracted.get("cv_en") else "fr"
        
        # Update experience.md
        self._update_experience_md(merged_data, lang)
        
        # Update motivations.md
        self._update_motivations_md(merged_data, lang)
        
        # Copy user templates to project templates
        self._sync_templates_to_project()
    
    def _sync_templates_to_project(self):
        """Sync user's base templates to project templates directory."""
        # CV templates
        for lang in ["en", "fr"]:
            user_cv = self.user_templates_dir / f"cv_base_{lang}.tex"
            if user_cv.exists():
                project_cv = self.templates_dir / f"cv_{lang}.tex"
                shutil.copy2(user_cv, project_cv)
                logger.info(f"  - Updated project template: cv_{lang}.tex")
        
        # Letter templates
        for lang in ["en", "fr"]:
            user_letter = self.user_templates_dir / f"letter_base_{lang}.tex"
            if user_letter.exists():
                project_letter = self.templates_dir / f"cover_letter_{lang}.tex"
                shutil.copy2(user_letter, project_letter)
                logger.info(f"  - Updated project template: cover_letter_{lang}.tex")
    
    # =========================================================================
    # Incremental Updates
    # =========================================================================
    
    def _incremental_update(self, update_text: str) -> int:
        """
        Add new information to existing profile via text command.
        
        Examples:
        - "Add AWS Solutions Architect certification obtained in January 2026"
        - "Add new job: Senior Developer at TechCorp since March 2025"
        - "Update phone number to +33 6 12 34 56 78"
        - "Add Python, Kubernetes to skills"
        - Partial LaTeX: "\\item AWS Solutions Architect - Amazon (2026)"
        """
        logger.info("=" * 60)
        logger.info("  INCREMENTAL PROFILE UPDATE")
        logger.info("=" * 60)
        
        if not update_text:
            logger.error("No update text provided")
            return 0
        
        logger.info(f"Processing: {update_text[:100]}...")
        
        # Load current state
        current_profile = self._load_current_profile()
        current_experience = self._load_user_experience()
        current_motivations = self._load_user_motivations()
        
        # Detect if this is LaTeX snippet
        is_latex = self._is_latex_content(update_text)
        if is_latex:
            logger.info("  - Detected LaTeX snippet")
        
        # Use LLM to process the update
        update_result = self._process_incremental_update(
            update_text,
            current_profile,
            current_experience,
            current_motivations,
            is_latex=is_latex
        )
        
        if not update_result:
            logger.error("Failed to process update")
            return 0
        
        # Backup and apply
        self._backup_current_files()
        
        if update_result.get("profile"):
            self._update_profile_yaml(update_result["profile"])
        
        if update_result.get("experience"):
            self._write_experience_md(update_result["experience"])
        
        if update_result.get("motivations"):
            self._write_motivations_md(update_result["motivations"])
        
        # Update LaTeX base templates if they exist
        self._update_user_latex_templates(update_result)
        
        logger.info("=" * 60)
        logger.info("  ✅ Profile updated!")
        logger.info("=" * 60)
        
        return 1
    
    def _is_latex_content(self, text: str) -> bool:
        """Check if text contains LaTeX commands."""
        latex_indicators = [
            r"\\item", r"\\textbf", r"\\textit", r"\\section", r"\\subsection",
            r"\\begin{", r"\\end{", r"\\newcommand", r"\\cventry", r"\\skill"
        ]
        return any(re.search(pattern, text) for pattern in latex_indicators)
    
    def _process_incremental_update(self, update_text: str, current_profile: Dict,
                                     current_experience: str, current_motivations: str,
                                     is_latex: bool = False) -> Optional[Dict]:
        """Process an incremental update using LLM."""
        context = "LaTeX snippet to parse" if is_latex else "Natural language update request"
        
        prompt = f"""You are updating a user's professional profile. Apply the requested changes.

## Current Profile (YAML)
```yaml
{yaml.dump(current_profile, default_flow_style=False, allow_unicode=True)}
```

## Current Experience Summary (truncated)
{current_experience[:1500] if current_experience else "Not set"}

## Update Request ({context})
{update_text}

## Instructions
Based on the update request, determine what needs to change and return a JSON object.
Only include sections that need updates.

Common update types:
- Adding certification → Update professional.certifications list
- Adding experience → Update experience list
- Adding skills → Append to primary_skills or secondary_skills
- Personal info change → Update personal section
- If LaTeX, parse the content and extract structured data

Return JSON:
{{
  "profile": {{ 
    // Only sections that changed
    "professional": {{
      "certifications": [...updated list...],
      "primary_skills": [...updated list...]
    }}
  }},
  "experience_additions": "New experience text to append to experience.md",
  "summary_update": "Updated summary if needed"
}}

Return ONLY valid JSON:"""
        
        try:
            response = self.llm_service.generate(prompt)
            result = self._parse_json_response(response)
            
            if result:
                # Merge profile updates with current
                if result.get("profile"):
                    merged_profile = self._deep_merge(current_profile, result["profile"])
                    result["profile"] = merged_profile
                
                # Build updated experience
                if result.get("experience_additions"):
                    result["experience"] = current_experience + "\n\n" + result["experience_additions"]
                elif current_experience:
                    result["experience"] = current_experience
                
                # Keep motivations unless changed
                if not result.get("motivations"):
                    result["motivations"] = current_motivations
                
                return result
                
        except Exception as e:
            logger.error(f"Incremental update processing failed: {e}")
        
        return None
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dicts, appending to lists instead of replacing."""
        result = base.copy()
        
        for key, value in override.items():
            if key in result:
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = self._deep_merge(result[key], value)
                elif isinstance(result[key], list) and isinstance(value, list):
                    # Append new items (deduplicated)
                    existing = set(str(x) for x in result[key])
                    for item in value:
                        if str(item) not in existing:
                            result[key].append(item)
                else:
                    result[key] = value
            else:
                result[key] = value
        
        return result
    
    def _update_user_latex_templates(self, update_result: Dict):
        """Update user's LaTeX base templates if they exist."""
        profile = update_result.get("profile", {})
        if not profile:
            return
        
        # Check for base CV templates
        for lang in ["en", "fr"]:
            base_template = self.user_templates_dir / f"cv_base_{lang}.tex"
            if base_template.exists():
                self._update_latex_template(base_template, profile, lang)
    
    def _update_latex_template(self, template_path: Path, profile: Dict, language: str):
        """Update a LaTeX template with new profile data."""
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            prompt = f"""Update this LaTeX CV template with new profile information.

## Current LaTeX Template
```latex
{content[:8000]}
```

## Profile Updates to Apply
```json
{json.dumps(profile, indent=2, default=str)}
```

## Instructions
1. Update any changed information (name, skills, certifications, experience)
2. Add any new items appropriately
3. Keep the exact LaTeX structure and formatting
4. Do NOT remove any existing content unless explicitly updated
5. Return the COMPLETE updated LaTeX document

Return ONLY LaTeX code (no markdown blocks):"""
            
            updated_content = self.llm_service.generate(prompt)
            
            # Clean markdown wrappers if present
            if "```latex" in updated_content:
                updated_content = updated_content.split("```latex")[1].split("```")[0]
            elif "```" in updated_content:
                parts = updated_content.split("```")
                if len(parts) >= 2:
                    updated_content = parts[1]
            
            # Save updated template
            with open(template_path, "w", encoding="utf-8") as f:
                f.write(updated_content.strip())
            
            logger.info(f"  - Updated LaTeX template: {template_path.name}")
            
            # Also sync to project templates
            project_template = self.templates_dir / f"cv_{language}.tex"
            if project_template.exists():
                shutil.copy2(template_path, project_template)
                logger.info(f"  - Synced to project: cv_{language}.tex")
                
        except Exception as e:
            logger.error(f"LaTeX template update failed: {e}")
    
    # =========================================================================
    # Full CV Update (legacy support)
    # =========================================================================
    
    def _full_cv_update(self, cv_path: str) -> int:
        """Full update from a CV file of any supported format."""
        logger.info("=" * 60)
        logger.info("  FULL CV UPDATE")
        logger.info("=" * 60)
        
        cv_file = Path(cv_path)
        if not cv_file.exists():
            logger.error(f"CV file not found: {cv_path}")
            return 0
        
        logger.info(f"Processing: {cv_file.name}")
        
        # Check if LaTeX
        if cv_file.suffix.lower() == ".tex":
            raw_content, text, structure = self.cv_parser.extract_latex_with_structure(cv_file)
            language = structure.get("language", "en")
            
            # Save as user base template
            template_name = f"cv_base_{language}.tex"
            self._save_user_template(cv_path, template_name)
            
            cv_text = text
        else:
            cv_text = self.cv_parser.extract_text(cv_file)
            language = self.language_detector.detect_text_language(cv_text or "")
        
        if not cv_text:
            logger.error("Failed to extract text from CV")
            return 0
        
        logger.info(f"  - Extracted {len(cv_text)} chars, language: {language}")
        
        # Extract profile data
        profile_data = self._extract_profile_data(cv_text, language)
        if not profile_data:
            logger.error("Failed to extract profile data")
            return 0
        
        # Backup and update
        self._backup_current_files()
        self._update_profile_yaml(profile_data)
        self._update_experience_md(profile_data, language)
        self._update_motivations_md(profile_data, language)
        
        logger.info("=" * 60)
        logger.info("  ✅ Profile updated from CV!")
        logger.info("=" * 60)
        
        return 1
    
    def _find_cv_in_uploads(self) -> Optional[str]:
        """Find CV file in uploads directory."""
        uploads_dirs = [Path("uploads"), Path("data/uploads")]
        
        for uploads_dir in uploads_dirs:
            if not uploads_dir.exists():
                continue
            
            cv_patterns = ["cv", "resume", "curriculum"]
            extensions = [".pdf", ".docx", ".doc", ".txt", ".md", ".tex"]
            
            # First look for files with CV-like names
            for file in uploads_dir.iterdir():
                if file.is_file():
                    name_lower = file.name.lower()
                    if file.suffix.lower() in extensions:
                        if any(pattern in name_lower for pattern in cv_patterns):
                            return str(file)
            
            # Return first matching extension
            for file in uploads_dir.iterdir():
                if file.suffix.lower() in extensions:
                    return str(file)
        
        return None
    
    # =========================================================================
    # Helper Methods - Loading Current State
    # =========================================================================
    
    def _load_current_profile(self) -> Dict:
        """Load current user profile from YAML."""
        if self.profile_path.exists():
            with open(self.profile_path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}
    
    def _load_user_experience(self) -> str:
        """Load current experience.md content."""
        exp_file = self.user_dir / "experience.md"
        if exp_file.exists():
            return exp_file.read_text(encoding="utf-8")
        return ""
    
    def _load_user_motivations(self) -> str:
        """Load current motivations.md content."""
        mot_file = self.user_dir / "motivations.md"
        if mot_file.exists():
            return mot_file.read_text(encoding="utf-8")
        return ""
    
    def _write_experience_md(self, content: str):
        """Write experience.md directly."""
        exp_file = self.user_dir / "experience.md"
        exp_file.parent.mkdir(parents=True, exist_ok=True)
        exp_file.write_text(content, encoding="utf-8")
        logger.info(f"Updated: {exp_file}")
    
    def _write_motivations_md(self, content: str):
        """Write motivations.md directly."""
        mot_file = self.user_dir / "motivations.md"
        mot_file.parent.mkdir(parents=True, exist_ok=True)
        mot_file.write_text(content, encoding="utf-8")
        logger.info(f"Updated: {mot_file}")
    
    # =========================================================================
    # LLM Extraction Methods
    # =========================================================================

    def _extract_profile_data(self, cv_text: str, language: str) -> Optional[Dict[str, Any]]:
        """Use LLM to extract structured profile data from CV text."""
        logger.info("Extracting profile data using LLM...")
        
        prompt = self._create_extraction_prompt(cv_text, language)
        
        try:
            response = self.llm_service.generate(prompt)
            
            # Parse JSON from response
            profile_data = self._parse_json_response(response)
            
            if profile_data:
                logger.info(f"Extracted profile for: {profile_data.get('personal', {}).get('first_name', 'Unknown')}")
                return profile_data
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
        
        return None
    
    def _create_extraction_prompt(self, cv_text: str, language: str) -> str:
        """Create prompt for CV data extraction."""
        return f"""You are an expert CV parser. Extract all information from this CV and return it as a valid JSON object.

## CV Content (Language: {language})
{cv_text}

## Required JSON Structure
Return ONLY a valid JSON object with this exact structure (fill in values from the CV):

```json
{{
  "personal": {{
    "first_name": "string",
    "last_name": "string",
    "email": "string",
    "phone": "string",
    "address": "string (city, country)",
    "linkedin": "string (URL or empty)",
    "github": "string (URL or empty)",
    "portfolio": "string (URL or empty)"
  }},
  "professional": {{
    "current_title": "string",
    "years_experience": number,
    "primary_skills": ["skill1", "skill2", ...],
    "secondary_skills": ["skill1", "skill2", ...],
    "certifications": [
      {{"name": "string", "issuer": "string", "year": number}}
    ],
    "languages": [
      {{"language": "string", "level": "string (Native/Fluent/Intermediate/Basic)"}}
    ]
  }},
  "education": [
    {{
      "degree": "string",
      "field": "string",
      "institution": "string",
      "year": number,
      "location": "string"
    }}
  ],
  "experience": [
    {{
      "title": "string",
      "company": "string",
      "location": "string",
      "start_date": "YYYY-MM",
      "end_date": "YYYY-MM or present",
      "highlights": ["achievement 1", "achievement 2", ...]
    }}
  ],
  "summary": "string (professional summary if present in CV)",
  "interests": ["interest1", "interest2", ...]
}}
```

## Instructions
1. Extract ALL information accurately from the CV
2. If a field is not found, use empty string "" or empty array []
3. For years_experience, calculate from work history if not stated
4. List skills in order of prominence in the CV
5. Include ALL certifications mentioned
6. Include ALL work experiences, ordered from most recent
7. Return ONLY the JSON object, no explanations or markdown

JSON:"""
    
    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response."""
        # Clean response
        response = response.strip()
        
        # Try to find JSON in response
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            response = response[start:end].strip()
        
        # Find JSON object boundaries
        if "{" in response:
            start = response.find("{")
            # Find matching closing brace
            depth = 0
            end = start
            for i, char in enumerate(response[start:], start):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            response = response[start:end]
        
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Response was: {response[:500]}...")
            return None
    
    def _backup_current_files(self):
        """Backup current profile files before updating."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.backups_dir / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        files_to_backup = [
            self.profile_path,
            self.user_dir / "experience.md",
            self.user_dir / "motivations.md"
        ]
        
        for file_path in files_to_backup:
            if file_path.exists():
                dest = backup_dir / file_path.name
                shutil.copy2(file_path, dest)
                logger.debug(f"Backed up: {file_path.name}")
        
        logger.info(f"Previous files backed up to: {backup_dir}")
    
    def _update_profile_yaml(self, data: Dict[str, Any]):
        """Update user_profile.yaml with extracted data."""
        # Load existing profile if exists
        existing = {}
        if self.profile_path.exists():
            with open(self.profile_path, "r") as f:
                existing = yaml.safe_load(f) or {}
        
        # Merge with new data (new data takes precedence)
        profile = {
            "personal": {**existing.get("personal", {}), **data.get("personal", {})},
            "professional": {**existing.get("professional", {}), **data.get("professional", {})},
            "education": data.get("education", existing.get("education", [])),
            "experience": data.get("experience", existing.get("experience", [])),
            "preferences": existing.get("preferences", {
                "preferred_languages": ["fr", "en"],
                "target_roles": [],
                "target_locations": [],
                "remote_preference": "hybrid"
            })
        }
        
        # Update target roles from experience
        if data.get("experience"):
            roles = [exp.get("title", "") for exp in data["experience"][:3]]
            profile["preferences"]["target_roles"] = [r for r in roles if r]
        
        # Ensure directory exists
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write updated profile
        with open(self.profile_path, "w") as f:
            yaml.dump(profile, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        logger.info(f"Updated: {self.profile_path}")
    
    def _update_experience_md(self, data: Dict[str, Any], language: str):
        """Update experience.md with extracted data."""
        personal = data.get("personal", {})
        professional = data.get("professional", {})
        experience = data.get("experience", [])
        education = data.get("education", [])
        
        # Generate markdown content
        if language == "fr":
            content = self._generate_experience_md_fr(personal, professional, experience, education, data)
        else:
            content = self._generate_experience_md_en(personal, professional, experience, education, data)
        
        # Write file
        exp_file = self.user_dir / "experience.md"
        with open(exp_file, "w") as f:
            f.write(content)
        
        logger.info(f"Updated: {exp_file}")
    
    def _generate_experience_md_en(self, personal, professional, experience, education, data) -> str:
        """Generate experience.md in English."""
        full_name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
        
        content = f"""# My Professional Experience

## Summary

{data.get('summary', f"{full_name} - {professional.get('current_title', 'Professional')} with {professional.get('years_experience', 0)} years of experience.")}

---

## Work Experience

"""
        # Add experience entries
        for exp in experience:
            content += f"""### {exp.get('title', 'Position')}
**Company**: {exp.get('company', '')}  
**Location**: {exp.get('location', '')}  
**Duration**: {exp.get('start_date', '')} - {exp.get('end_date', 'Present')}  

**Key Achievements**:
"""
            for highlight in exp.get('highlights', []):
                content += f"- {highlight}\n"
            content += "\n---\n\n"
        
        # Technical skills
        content += """## Technical Skills

### Expert Level
"""
        for skill in professional.get('primary_skills', [])[:5]:
            content += f"- {skill}\n"
        
        content += """
### Proficient Level
"""
        for skill in professional.get('secondary_skills', [])[:5]:
            content += f"- {skill}\n"
        
        # Certifications
        certs = professional.get('certifications', [])
        if certs:
            content += """
---

## Certifications & Training

"""
            for cert in certs:
                content += f"- **{cert.get('name', '')}** - {cert.get('issuer', '')} ({cert.get('year', '')})\n"
        
        # Languages
        langs = professional.get('languages', [])
        if langs:
            content += """
---

## Languages

| Language | Level |
|----------|-------|
"""
            for lang in langs:
                content += f"| {lang.get('language', '')} | {lang.get('level', '')} |\n"
        
        # Education
        if education:
            content += """
---

## Education

"""
            for edu in education:
                content += f"- **{edu.get('degree', '')}** in {edu.get('field', '')} - {edu.get('institution', '')} ({edu.get('year', '')})\n"
        
        return content
    
    def _generate_experience_md_fr(self, personal, professional, experience, education, data) -> str:
        """Generate experience.md in French."""
        full_name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
        
        content = f"""# Mon Expérience Professionnelle

## Résumé

{data.get('summary', f"{full_name} - {professional.get('current_title', 'Professionnel')} avec {professional.get('years_experience', 0)} années d'expérience.")}

---

## Expérience Professionnelle

"""
        # Add experience entries
        for exp in experience:
            content += f"""### {exp.get('title', 'Poste')}
**Entreprise**: {exp.get('company', '')}  
**Lieu**: {exp.get('location', '')}  
**Durée**: {exp.get('start_date', '')} - {exp.get('end_date', 'Présent')}  

**Réalisations Clés**:
"""
            for highlight in exp.get('highlights', []):
                content += f"- {highlight}\n"
            content += "\n---\n\n"
        
        # Technical skills
        content += """## Compétences Techniques

### Niveau Expert
"""
        for skill in professional.get('primary_skills', [])[:5]:
            content += f"- {skill}\n"
        
        content += """
### Niveau Avancé
"""
        for skill in professional.get('secondary_skills', [])[:5]:
            content += f"- {skill}\n"
        
        # Certifications
        certs = professional.get('certifications', [])
        if certs:
            content += """
---

## Certifications & Formations

"""
            for cert in certs:
                content += f"- **{cert.get('name', '')}** - {cert.get('issuer', '')} ({cert.get('year', '')})\n"
        
        # Languages
        langs = professional.get('languages', [])
        if langs:
            content += """
---

## Langues

| Langue | Niveau |
|--------|--------|
"""
            for lang in langs:
                content += f"| {lang.get('language', '')} | {lang.get('level', '')} |\n"
        
        # Education
        if education:
            content += """
---

## Formation

"""
            for edu in education:
                content += f"- **{edu.get('degree', '')}** en {edu.get('field', '')} - {edu.get('institution', '')} ({edu.get('year', '')})\n"
        
        return content
    
    def _update_motivations_md(self, data: Dict[str, Any], language: str):
        """Update motivations.md with extracted data."""
        personal = data.get("personal", {})
        professional = data.get("professional", {})
        interests = data.get("interests", [])
        experience = data.get("experience", [])
        
        # Extract relevant info for motivations
        skills = professional.get("primary_skills", [])[:5]
        recent_roles = [exp.get("title", "") for exp in experience[:2]]
        
        if language == "fr":
            content = self._generate_motivations_md_fr(skills, recent_roles, interests)
        else:
            content = self._generate_motivations_md_en(skills, recent_roles, interests)
        
        # Write file
        mot_file = self.user_dir / "motivations.md"
        with open(mot_file, "w") as f:
            f.write(content)
        
        logger.info(f"Updated: {mot_file}")
    
    def _generate_motivations_md_en(self, skills, roles, interests) -> str:
        """Generate motivations.md in English."""
        skills_str = ", ".join(skills) if skills else "various technologies"
        roles_str = " and ".join(roles[:2]) if roles else "professional roles"
        
        content = f"""# My Motivations

## Why I'm Looking for New Opportunities

I am seeking new challenges that align with my passion for {skills_str}. With experience as {roles_str}, I want to contribute to projects that make a meaningful impact while continuing to grow professionally.

## What I'm Looking For

### Company Culture
- Collaborative environment
- Focus on learning and growth
- Work-life balance
- Innovation-driven

### Role Expectations
- Technical challenges
- Opportunity to mentor and be mentored
- Cross-functional collaboration
- Impact on product decisions

### Industry Interests
"""
        for interest in interests[:5] if interests else ["Technology", "Innovation"]:
            content += f"- {interest}\n"
        
        content += f"""
## Key Strengths I Bring

1. **Technical Expertise**: Strong background in {skills_str}
2. **Problem Solving**: Analytical approach to complex challenges
3. **Communication**: Effective collaboration with diverse teams
4. **Adaptability**: Quick learner, comfortable with new technologies

## Career Goals

### Short-term (1-2 years)
- Deepen expertise in current technology stack
- Take on leadership responsibilities
- Contribute to impactful projects

### Long-term (3-5 years)
- Grow into senior/lead technical role
- Mentor junior developers
- Drive architectural decisions

## Values That Matter to Me

- Continuous learning
- Clean, maintainable code
- Team success over individual glory
- Making technology accessible
- Ethical development practices
"""
        return content
    
    def _generate_motivations_md_fr(self, skills, roles, interests) -> str:
        """Generate motivations.md in French."""
        skills_str = ", ".join(skills) if skills else "diverses technologies"
        roles_str = " et ".join(roles[:2]) if roles else "rôles professionnels"
        
        content = f"""# Mes Motivations

## Pourquoi je recherche de nouvelles opportunités

Je recherche de nouveaux défis en accord avec ma passion pour {skills_str}. Avec mon expérience en tant que {roles_str}, je souhaite contribuer à des projets ayant un impact significatif tout en continuant à évoluer professionnellement.

## Ce que je recherche

### Culture d'entreprise
- Environnement collaboratif
- Focus sur l'apprentissage et la croissance
- Équilibre vie professionnelle/personnelle
- Orienté innovation

### Attentes du rôle
- Défis techniques
- Opportunité de mentorer et d'être mentoré
- Collaboration transversale
- Impact sur les décisions produit

### Secteurs d'intérêt
"""
        for interest in interests[:5] if interests else ["Technologie", "Innovation"]:
            content += f"- {interest}\n"
        
        content += f"""
## Forces clés que j'apporte

1. **Expertise technique**: Solide expérience en {skills_str}
2. **Résolution de problèmes**: Approche analytique des défis complexes
3. **Communication**: Collaboration efficace avec des équipes diverses
4. **Adaptabilité**: Apprentissage rapide, à l'aise avec les nouvelles technologies

## Objectifs de carrière

### Court terme (1-2 ans)
- Approfondir l'expertise sur le stack technologique actuel
- Prendre des responsabilités de leadership
- Contribuer à des projets à fort impact

### Long terme (3-5 ans)
- Évoluer vers un rôle technique senior/lead
- Mentorer des développeurs juniors
- Piloter les décisions architecturales

## Valeurs qui comptent pour moi

- Apprentissage continu
- Code propre et maintenable
- Succès de l'équipe avant le succès individuel
- Rendre la technologie accessible
- Pratiques de développement éthiques
"""
        return content
