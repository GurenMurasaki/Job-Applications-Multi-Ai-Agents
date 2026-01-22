"""
Language Detector Service

Detects appropriate language for job applications based on:
- Job description language
- Job location/country
- Explicit language requirements
"""

from typing import Optional
from loguru import logger


class LanguageDetector:
    """
    Service for detecting appropriate application language.
    """
    
    def __init__(self, config: dict):
        """
        Initialize the language detector.
        
        Args:
            config: Language configuration dictionary
        """
        self.default_language = config.get("default", "en")
        self.country_mapping = config.get("country_mapping", {
            "France": "fr",
            "Belgium": "fr",
            "Switzerland": "fr",
            "Canada": "en",
            "UK": "en",
            "USA": "en",
            "Germany": "de",
            "Spain": "es",
            "Italy": "it"
        })
        
        # Try to import langdetect
        try:
            from langdetect import detect, DetectorFactory
            DetectorFactory.seed = 0  # For consistent results
            self._langdetect_available = True
        except ImportError:
            self._langdetect_available = False
            logger.warning("langdetect not available, using fallback detection")
    
    def detect_job_language(self, job) -> str:
        """
        Detect the appropriate language for a job application.
        
        Args:
            job: NormalizedJobOffer object
            
        Returns:
            Language code ('en', 'fr', etc.)
        """
        # Priority 1: Check for explicit language requirements
        explicit_lang = self._check_explicit_requirements(job.description)
        if explicit_lang:
            logger.debug(f"Explicit language requirement found: {explicit_lang}")
            return explicit_lang
        
        # Priority 2: Check country
        if job.country:
            country_lang = self._get_language_by_country(job.country)
            if country_lang:
                logger.debug(f"Language by country ({job.country}): {country_lang}")
                return country_lang
        
        # Priority 3: Check location for country hints
        if job.location:
            location_lang = self._detect_from_location(job.location)
            if location_lang:
                logger.debug(f"Language by location: {location_lang}")
                return location_lang
        
        # Priority 4: Detect from description text
        if job.description and self._langdetect_available:
            text_lang = self._detect_from_text(job.description)
            if text_lang:
                logger.debug(f"Language detected from text: {text_lang}")
                return text_lang
        
        # Fallback to default
        logger.debug(f"Using default language: {self.default_language}")
        return self.default_language
    
    def _check_explicit_requirements(self, description: str) -> Optional[str]:
        """Check for explicit language requirements in description."""
        if not description:
            return None
        
        desc_lower = description.lower()
        
        # English indicators
        english_patterns = [
            "english required",
            "english is required",
            "fluent in english",
            "english fluency",
            "english-speaking",
            "must speak english",
            "native english",
            "english native"
        ]
        
        # French indicators
        french_patterns = [
            "français requis",
            "français exigé",
            "maîtrise du français",
            "francophone",
            "langue française",
            "french required",
            "fluent in french",
            "french fluency"
        ]
        
        for pattern in english_patterns:
            if pattern in desc_lower:
                return "en"
        
        for pattern in french_patterns:
            if pattern in desc_lower:
                return "fr"
        
        return None
    
    def _get_language_by_country(self, country: str) -> Optional[str]:
        """Get language based on country."""
        if not country:
            return None
        
        # Normalize country name
        country_normalized = country.strip().title()
        
        # Check direct mapping
        if country_normalized in self.country_mapping:
            return self.country_mapping[country_normalized]
        
        # Check for partial matches
        country_lower = country.lower()
        for mapped_country, lang in self.country_mapping.items():
            if mapped_country.lower() in country_lower or country_lower in mapped_country.lower():
                return lang
        
        return None
    
    def _detect_from_location(self, location: str) -> Optional[str]:
        """Detect language from location string."""
        if not location:
            return None
        
        location_lower = location.lower()
        
        # French cities/regions
        french_indicators = [
            "paris", "lyon", "marseille", "toulouse", "nice", "nantes",
            "strasbourg", "bordeaux", "lille", "france", "île-de-france"
        ]
        
        # English-speaking locations
        english_indicators = [
            "london", "new york", "san francisco", "los angeles", "chicago",
            "boston", "seattle", "uk", "usa", "united states", "united kingdom",
            "australia", "sydney", "melbourne", "toronto"
        ]
        
        for indicator in french_indicators:
            if indicator in location_lower:
                return "fr"
        
        for indicator in english_indicators:
            if indicator in location_lower:
                return "en"
        
        return None
    
    def _detect_from_text(self, text: str) -> Optional[str]:
        """Detect language from text using langdetect."""
        if not self._langdetect_available or not text:
            return None
        
        try:
            from langdetect import detect
            
            # Use first 500 characters for detection
            sample = text[:500]
            detected = detect(sample)
            
            # Map to our supported languages
            if detected in ["en", "fr", "de", "es", "it"]:
                return detected
            
            return None
            
        except Exception as e:
            logger.debug(f"Language detection failed: {e}")
            return None
    
    def detect_text_language(self, text: str) -> str:
        """
        Detect language of a text string.
        
        Args:
            text: Text to analyze
            
        Returns:
            Language code
        """
        if self._langdetect_available and text:
            try:
                from langdetect import detect
                return detect(text)
            except Exception:
                pass
        
        return self.default_language
