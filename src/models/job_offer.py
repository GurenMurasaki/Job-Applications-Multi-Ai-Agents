"""
Job Offer Model

Defines the normalized job offer structure and schema normalization
for different job sources (LinkedIn, Indeed, etc.)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from loguru import logger


@dataclass
class NormalizedJobOffer:
    """
    Normalized job offer data structure.
    
    All job data from different sources is converted to this format.
    """
    job_id: str
    source: str  # linkedin, indeed, other
    title: str
    company: str
    location: str
    description: str
    requirements: List[str] = field(default_factory=list)
    country: Optional[str] = None
    contact_email: Optional[str] = None
    apply_url: Optional[str] = None
    salary: Optional[str] = None
    job_type: Optional[str] = None  # full-time, part-time, contract
    experience_level: Optional[str] = None
    language: str = "en"
    raw_data: Dict[str, Any] = field(default_factory=dict)
    extracted_at: str = ""
    
    def __post_init__(self):
        if not self.extracted_at:
            self.extracted_at = datetime.utcnow().isoformat() + "Z"


def normalize_job_data(raw_data: Dict[str, Any]) -> Optional[NormalizedJobOffer]:
    """
    Normalize job data from various sources to a standard format.
    
    Args:
        raw_data: Raw job data dictionary from Kafka
        
    Returns:
        NormalizedJobOffer if successful, None otherwise
    """
    if not raw_data:
        return None
    
    # Detect source
    source = raw_data.get("source", "").lower()
    
    if not source:
        # Try to detect from data structure
        source = _detect_source(raw_data)
    
    # Normalize based on source
    normalizers = {
        "linkedin": _normalize_linkedin,
        "indeed": _normalize_indeed,
        "glassdoor": _normalize_glassdoor,
        "other": _normalize_generic
    }
    
    normalizer = normalizers.get(source, _normalize_generic)
    
    try:
        job = normalizer(raw_data)
        if job:
            job.source = source
            job.raw_data = raw_data
            logger.debug(f"Normalized job from {source}: {job.title}")
            return job
    except Exception as e:
        logger.error(f"Failed to normalize job data: {e}")
    
    return None


def _detect_source(data: Dict[str, Any]) -> str:
    """Detect job source from data structure."""
    # LinkedIn-specific fields
    if "job_id" in data and "linkedin" in str(data.get("apply_url", "")):
        return "linkedin"
    
    # Indeed-specific fields
    if "employer" in data or ("id" in data and data.get("id", "").startswith("indeed")):
        return "indeed"
    
    # Default
    return "other"


def _normalize_linkedin(data: Dict[str, Any]) -> NormalizedJobOffer:
    """Normalize LinkedIn job data."""
    # Extract requirements from description or dedicated field
    requirements = data.get("requirements", [])
    if isinstance(requirements, str):
        requirements = [r.strip() for r in requirements.split(",") if r.strip()]
    
    # Extract country from location
    location = data.get("location", "")
    country = _extract_country(location)
    
    return NormalizedJobOffer(
        job_id=data.get("job_id", data.get("id", _generate_id("linkedin"))),
        source="linkedin",
        title=data.get("title", data.get("position", "Unknown Position")),
        company=data.get("company", data.get("company_name", "Unknown Company")),
        location=location,
        country=country,
        description=data.get("description", data.get("job_description", "")),
        requirements=requirements,
        contact_email=data.get("contact_email", data.get("email", "")),
        apply_url=data.get("apply_url", data.get("url", "")),
        salary=data.get("salary", data.get("salary_range", "")),
        job_type=data.get("job_type", data.get("employment_type", "")),
        experience_level=data.get("experience_level", data.get("seniority", "")),
        extracted_at=data.get("extracted_at", data.get("posted_date", ""))
    )


def _normalize_indeed(data: Dict[str, Any]) -> NormalizedJobOffer:
    """Normalize Indeed job data."""
    # Indeed uses different field names
    requirements = data.get("skills", data.get("requirements", []))
    if isinstance(requirements, str):
        requirements = [r.strip() for r in requirements.split(",") if r.strip()]
    
    # Location handling
    city = data.get("city", "")
    country = data.get("country", "")
    location = f"{city}, {country}".strip(", ")
    
    return NormalizedJobOffer(
        job_id=data.get("id", data.get("job_id", _generate_id("indeed"))),
        source="indeed",
        title=data.get("position", data.get("title", "Unknown Position")),
        company=data.get("employer", data.get("company", "Unknown Company")),
        location=location,
        country=country,
        description=data.get("job_description", data.get("description", "")),
        requirements=requirements,
        contact_email=data.get("email", data.get("contact_email", "")),
        apply_url=data.get("apply_url", data.get("url", "")),
        salary=data.get("salary", ""),
        job_type=data.get("job_type", ""),
        extracted_at=data.get("timestamp", data.get("extracted_at", ""))
    )


def _normalize_glassdoor(data: Dict[str, Any]) -> NormalizedJobOffer:
    """Normalize Glassdoor job data."""
    requirements = data.get("requirements", data.get("qualifications", []))
    if isinstance(requirements, str):
        requirements = [r.strip() for r in requirements.split(",") if r.strip()]
    
    location = data.get("location", "")
    country = _extract_country(location)
    
    return NormalizedJobOffer(
        job_id=data.get("job_id", data.get("id", _generate_id("glassdoor"))),
        source="glassdoor",
        title=data.get("title", data.get("job_title", "Unknown Position")),
        company=data.get("company", data.get("employer_name", "Unknown Company")),
        location=location,
        country=country,
        description=data.get("description", data.get("job_description", "")),
        requirements=requirements,
        contact_email=data.get("contact_email", ""),
        apply_url=data.get("apply_url", data.get("listing_url", "")),
        salary=data.get("salary_estimate", data.get("salary", "")),
        job_type=data.get("employment_type", ""),
        extracted_at=data.get("posted_date", data.get("extracted_at", ""))
    )


def _normalize_generic(data: Dict[str, Any]) -> NormalizedJobOffer:
    """Normalize generic job data with best-effort field mapping."""
    # Try various field names for each attribute
    title_fields = ["title", "position", "job_title", "role", "name"]
    company_fields = ["company", "employer", "company_name", "organization"]
    location_fields = ["location", "city", "place", "address"]
    description_fields = ["description", "job_description", "details", "content"]
    requirements_fields = ["requirements", "skills", "qualifications", "must_have"]
    email_fields = ["email", "contact_email", "contact", "apply_email"]
    url_fields = ["url", "apply_url", "link", "application_url"]
    
    def get_first(fields):
        for f in fields:
            if f in data and data[f]:
                return data[f]
        return ""
    
    # Handle requirements
    requirements = get_first(requirements_fields)
    if isinstance(requirements, str):
        requirements = [r.strip() for r in requirements.split(",") if r.strip()]
    elif not isinstance(requirements, list):
        requirements = []
    
    location = get_first(location_fields)
    country = _extract_country(location) or data.get("country", "")
    
    return NormalizedJobOffer(
        job_id=data.get("job_id", data.get("id", _generate_id("other"))),
        source="other",
        title=get_first(title_fields) or "Unknown Position",
        company=get_first(company_fields) or "Unknown Company",
        location=location,
        country=country,
        description=get_first(description_fields),
        requirements=requirements,
        contact_email=get_first(email_fields),
        apply_url=get_first(url_fields),
        salary=data.get("salary", data.get("salary_range", "")),
        job_type=data.get("job_type", data.get("type", "")),
        extracted_at=data.get("extracted_at", data.get("timestamp", ""))
    )


def _extract_country(location: str) -> Optional[str]:
    """Extract country from location string."""
    if not location:
        return None
    
    location_lower = location.lower()
    
    # Common country patterns
    countries = {
        "france": "France",
        "fr": "France",
        "united states": "USA",
        "usa": "USA",
        "us": "USA",
        "united kingdom": "UK",
        "uk": "UK",
        "germany": "Germany",
        "de": "Germany",
        "canada": "Canada",
        "ca": "Canada",
        "spain": "Spain",
        "es": "Spain",
        "italy": "Italy",
        "it": "Italy",
        "belgium": "Belgium",
        "be": "Belgium",
        "switzerland": "Switzerland",
        "ch": "Switzerland"
    }
    
    for pattern, country in countries.items():
        if pattern in location_lower:
            return country
    
    return None


def _generate_id(prefix: str) -> str:
    """Generate a unique job ID."""
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:8]}"
