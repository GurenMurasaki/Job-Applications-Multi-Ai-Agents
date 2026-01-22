# Job Application Multi-Agent System - Technical Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Data Flow](#data-flow)
4. [Agent Specifications](#agent-specifications)
5. [Kafka Integration](#kafka-integration)
6. [Configuration](#configuration)
7. [Data Schemas](#data-schemas)
8. [Folder Structure](#folder-structure)
9. [Language Detection](#language-detection)
10. [Gmail Integration](#gmail-integration)
11. [Usage Guide](#usage-guide)
12. [Stopping the System](#stopping-the-system)
13. [Profile Updater Agent](#profile-updater-agent-independent)
14. [Troubleshooting](#troubleshooting)
15. [Future Enhancements](#future-enhancements)

---

## Overview

This system implements a **sequential multi-agent architecture** designed for resource-constrained environments (single GPU). Each agent operates independently but completes the work of the previous one, forming a pipeline for automated job application processing.

### Key Design Principles

1. **Sequential Execution**: Agents run one at a time to conserve GPU/memory resources
2. **Platform Agnostic**: Supports various job data schemas (LinkedIn, Indeed, etc.)
3. **Stateful Processing**: Each job gets its own folder with complete state tracking
4. **Language Aware**: Automatically detects and adapts to job offer language
5. **Human-in-the-Loop**: Creates drafts for manual review before sending
6. **Graceful Shutdown**: Finish current job before stopping, with force stop option
7. **Resumable Processing**: Can restart from where it left off after stop/crash

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Job Application Agents                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │  Kafka Consumer  │───▶│  Agent Manager   │───▶│  State Manager   │  │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘  │
│           │                       │                       │             │
│           ▼                       ▼                       ▼             │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                         Agent Pool (Sequential)                   │  │
│  │  ┌─────────────────────┐    ┌─────────────────────────────────┐  │  │
│  │  │ CV Customizer Agent │───▶│ Cover Letter & Gmail Draft Agent│  │  │
│  │  └─────────────────────┘    └─────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │   LLM Service    │    │  LaTeX Service   │    │  Gmail Service   │  │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology |
|-----------|------------|
| Message Queue | Apache Kafka |
| LLM | Ollama (local) / OpenAI API |
| Document Processing | LaTeX (pdflatex) |
| Email | Gmail API |
| Language | Python 3.10+ |
| Data Format | JSON, Markdown, YAML |

---

## Data Flow

### Complete Pipeline

```
1. DroidRun extracts job post from mobile app
                    │
                    ▼
2. Job data published to Kafka topic
                    │
                    ▼
3. CV Customizer Agent:
   ├── Consume Kafka message
   ├── Normalize job data (handle different schemas)
   ├── Create job folder: data/jobs/{job_id}/
   ├── Generate job_details.md
   ├── Generate user_context.md
   ├── Customize CV using LLM
   ├── Compile LaTeX → PDF
   └── Update status.json (cv_ready: true)
                    │
                    ▼
4. [Repeat step 3 for all Kafka messages]
                    │
                    ▼
5. Cover Letter & Gmail Draft Agent:
   ├── Scan data/jobs/ for unprocessed folders
   ├── For each unprocessed job:
   │   ├── Read job_details.md & user_context.md
   │   ├── Detect language (French/English)
   │   ├── Generate cover letter using LLM
   │   ├── Compile LaTeX → PDF
   │   ├── Create Gmail draft with attachments
   │   └── Update status.json (draft_ready: true)
   └── Mark folder as processed
                    │
                    ▼
6. Human reviews and sends drafts manually
```

---

## Agent Specifications

### Agent 1: CV Customizer Agent

**Purpose**: Consume job offers from Kafka and create customized CVs

**Input**:
- Kafka messages with job offer data (various schemas)
- User base CV template (LaTeX)
- User profile and experience

**Output** (per job):
```
data/jobs/{job_id}/
├── job_details.md      # Structured job information
├── user_context.md     # Relevant user info for this job
├── cv_customized.tex   # Tailored LaTeX CV
├── cv_customized.pdf   # Compiled PDF
└── status.json         # Processing status
```

**Processing Logic**:
1. Consume message from Kafka
2. Detect source platform (LinkedIn, Indeed, etc.)
3. Normalize to internal job schema
4. Extract key requirements and skills
5. Match with user skills/experience
6. Use LLM to customize CV sections
7. Compile LaTeX to PDF
8. Update status and continue

**Status Flags**:
```json
{
  "job_id": "uuid",
  "source": "linkedin",
  "cv_ready": true,
  "cover_letter_ready": false,
  "draft_ready": false,
  "processed": false,
  "created_at": "2026-01-22T10:00:00Z",
  "updated_at": "2026-01-22T10:05:00Z"
}
```

### Agent 2: Cover Letter & Gmail Draft Agent

**Purpose**: Create cover letters and Gmail drafts for all pending jobs

**Activation**: When Agent 1 has consumed all Kafka messages

**Input**:
- Job folders with `cv_ready: true` and `draft_ready: false`
- Cover letter templates (French/English)
- User motivations and experience

**Output** (per job):
```
data/jobs/{job_id}/
├── ... (existing files)
├── cover_letter.tex    # Generated cover letter
├── cover_letter.pdf    # Compiled PDF
├── email_draft.json    # Email metadata
└── status.json         # Updated with draft_ready: true
```

**Gmail Draft Content**:
- **To**: Extracted from job description or company contact
- **Subject**: Position-specific subject line
- **Body**: Professional email in appropriate language
- **Attachments**: CV PDF + Cover Letter PDF

**Language Selection Logic**:
```python
def select_language(job_details):
    # Priority 1: Explicit language requirement in job
    if job_details.required_language:
        return job_details.required_language
    
    # Priority 2: Country-based default
    if job_details.country == "France":
        return "fr"
    elif job_details.country in ["UK", "USA", "Canada"]:
        return "en"
    
    # Priority 3: Detect from job description text
    return detect_language(job_details.description)
```

---

## Kafka Integration

### Topic Structure

```
job-applications/
├── linkedin-jobs      # Jobs from LinkedIn
├── indeed-jobs        # Jobs from Indeed
├── other-jobs         # Other sources
└── processing-status  # Status updates (optional)
```

### Consumer Configuration

```yaml
kafka:
  bootstrap_servers: "localhost:9092"
  group_id: "job-application-agents"
  topics:
    - "linkedin-jobs"
    - "indeed-jobs"
    - "other-jobs"
  auto_offset_reset: "earliest"
  enable_auto_commit: true
  consumer_timeout_ms: 30000  # 30s timeout to detect end of messages
```

### Message Format Examples

**LinkedIn Job**:
```json
{
  "source": "linkedin",
  "job_id": "linkedin_12345",
  "title": "Software Engineer",
  "company": "TechCorp",
  "location": "Paris, France",
  "description": "We are looking for...",
  "requirements": ["Python", "Django", "PostgreSQL"],
  "contact_email": "hr@techcorp.com",
  "apply_url": "https://linkedin.com/jobs/...",
  "posted_date": "2026-01-20",
  "extracted_at": "2026-01-22T09:00:00Z"
}
```

**Indeed Job**:
```json
{
  "source": "indeed",
  "id": "indeed_67890",
  "position": "Backend Developer",
  "employer": "StartupXYZ",
  "city": "Lyon",
  "country": "France",
  "job_description": "Join our team...",
  "skills": "Python, FastAPI, Redis",
  "email": "jobs@startupxyz.com",
  "timestamp": "2026-01-21T15:30:00Z"
}
```

### Schema Normalization

The system normalizes various schemas to internal format:

```python
@dataclass
class NormalizedJobOffer:
    job_id: str
    source: str  # linkedin, indeed, etc.
    title: str
    company: str
    location: str
    country: str
    description: str
    requirements: List[str]
    contact_email: Optional[str]
    apply_url: Optional[str]
    language: str  # detected or specified
    raw_data: dict  # original message
    extracted_at: datetime
```

---

## Configuration

### Main Configuration (config/config.yaml)

```yaml
# Kafka Configuration
kafka:
  bootstrap_servers: "localhost:9092"
  group_id: "job-application-agents"
  topics:
    - "linkedin-jobs"
    - "indeed-jobs"
  consumer_timeout_ms: 30000

# LLM Configuration
llm:
  provider: "ollama"  # or "openai"
  model: "llama3.2"   # Default for all agents
  base_url: "http://localhost:11434"
  temperature: 0.7
  max_tokens: 4096
  
  # Per-agent customization (optional)
  # Set enabled: true to use custom model for specific agent
  agents:
    cv_customizer:
      enabled: false      # Set to true to override
      model: "llama3.2"
    cover_letter:
      enabled: false
      model: "llama3.2"   # Use better model for writing
    profile_updater:
      enabled: false
      model: "llama3.2"

# LaTeX Configuration
latex:
  compiler: "pdflatex"
  output_format: "pdf"
  
# Gmail Configuration
gmail:
  credentials_file: "config/gmail_credentials.json"
  token_file: "config/gmail_token.json"
  scopes:
    - "https://www.googleapis.com/auth/gmail.compose"
    - "https://www.googleapis.com/auth/gmail.modify"

# Paths
paths:
  jobs_dir: "data/jobs"
  user_dir: "data/user"
  templates_dir: "templates"
  processed_dir: "data/processed"

# Processing
processing:
  batch_size: 10
  retry_attempts: 3
  retry_delay: 5
```

### User Profile (config/user_profile.yaml)

```yaml
personal:
  first_name: "John"
  last_name: "Doe"
  email: "john.doe@gmail.com"
  phone: "+33 6 XX XX XX XX"
  address: "Paris, France"
  linkedin: "https://linkedin.com/in/johndoe"
  github: "https://github.com/johndoe"

professional:
  current_title: "Software Engineer"
  years_experience: 5
  primary_skills:
    - Python
    - Django
    - FastAPI
    - PostgreSQL
    - Docker
  secondary_skills:
    - JavaScript
    - React
    - AWS
  languages:
    - language: "French"
      level: "Native"
    - language: "English"
      level: "Fluent"

preferences:
  preferred_languages: ["fr", "en"]
  target_roles:
    - "Backend Developer"
    - "Full Stack Developer"
    - "Software Engineer"
  target_locations:
    - "Paris"
    - "Remote"
```

---

## Data Schemas

### Job Folder Structure

```
data/jobs/{job_id}/
├── job_details.md      # Human-readable job summary
├── user_context.md     # Relevant user info for this job
├── cv_customized.tex   # Tailored CV source
├── cv_customized.pdf   # Compiled CV
├── cover_letter.tex    # Cover letter source
├── cover_letter.pdf    # Compiled cover letter
├── email_draft.json    # Gmail draft metadata
├── status.json         # Processing status
└── raw_job_data.json   # Original Kafka message
```

### job_details.md Format

```markdown
# Job Details

## Position
**Title**: Software Engineer
**Company**: TechCorp
**Location**: Paris, France

## Description
[Full job description here]

## Requirements
- Python (Required)
- Django (Required)
- PostgreSQL (Preferred)

## Contact
**Email**: hr@techcorp.com
**Apply URL**: https://...

## Metadata
- **Source**: LinkedIn
- **Job ID**: linkedin_12345
- **Posted**: 2026-01-20
- **Extracted**: 2026-01-22T09:00:00Z
- **Language**: French
```

### user_context.md Format

```markdown
# User Context for This Application

## Matching Skills
- Python (5 years) ✓ Required
- Django (3 years) ✓ Required
- PostgreSQL (4 years) ✓ Preferred

## Relevant Experience
- Backend Developer at XYZ Corp (2023-Present)
  - Built REST APIs with Django
  - Managed PostgreSQL databases

## Key Motivations
- Interest in TechCorp's mission
- Opportunity for growth in Paris

## Language Selection
- **CV Language**: French
- **Cover Letter Language**: French
- **Email Language**: French
- **Reason**: Job is in France, no English requirement specified
```

### status.json Format

```json
{
  "job_id": "linkedin_12345",
  "source": "linkedin",
  "stages": {
    "kafka_consumed": {
      "completed": true,
      "timestamp": "2026-01-22T10:00:00Z"
    },
    "cv_customized": {
      "completed": true,
      "timestamp": "2026-01-22T10:02:00Z"
    },
    "cover_letter_generated": {
      "completed": true,
      "timestamp": "2026-01-22T10:05:00Z"
    },
    "gmail_draft_created": {
      "completed": true,
      "timestamp": "2026-01-22T10:06:00Z",
      "draft_id": "draft_abc123"
    }
  },
  "language": "fr",
  "processed": false,
  "errors": [],
  "created_at": "2026-01-22T10:00:00Z",
  "updated_at": "2026-01-22T10:06:00Z"
}
```

---

## Language Detection

### Detection Strategy

1. **Explicit Requirement**: Check if job specifies required language
2. **Country-Based**: Default language by country
3. **Text Analysis**: Analyze job description language

### Country-Language Mapping

| Country | Default Language |
|---------|------------------|
| France | French |
| Belgium | French (check region) |
| Switzerland | French/German (check region) |
| Canada | English/French (check province) |
| UK, USA, Australia | English |
| Germany | German |
| Others | English |

### Override Rules

- If job explicitly requires English → Use English
- If job is remote for international company → Use English
- If contact email domain suggests language → Consider it

---

## Gmail Integration

### Draft Structure

```json
{
  "to": "hr@company.com",
  "subject": "Candidature - Software Engineer - John Doe",
  "body": "...",
  "attachments": [
    {
      "filename": "CV_John_Doe.pdf",
      "path": "data/jobs/xxx/cv_customized.pdf"
    },
    {
      "filename": "Lettre_Motivation_John_Doe.pdf",
      "path": "data/jobs/xxx/cover_letter.pdf"
    }
  ]
}
```

### Email Templates

**French Template**:
```
Objet: Candidature - {position} - {full_name}

Madame, Monsieur,

Je me permets de vous adresser ma candidature pour le poste de {position} 
au sein de {company}.

Vous trouverez ci-joint mon CV ainsi que ma lettre de motivation.

Je reste à votre disposition pour tout entretien.

Cordialement,
{full_name}
```

**English Template**:
```
Subject: Application - {position} - {full_name}

Dear Hiring Manager,

I am writing to apply for the {position} position at {company}.

Please find attached my CV and cover letter.

I look forward to discussing this opportunity with you.

Best regards,
{full_name}
```

---

## Usage Guide

### Initial Setup

1. **Install Dependencies**:
```bash
cd job-application-agents
pip install -r requirements.txt
```

2. **Configure Kafka**:
```bash
# Ensure Kafka is running
kafka-server-start.sh config/server.properties

# Create topics
kafka-topics.sh --create --topic linkedin-jobs --bootstrap-server localhost:9092
kafka-topics.sh --create --topic indeed-jobs --bootstrap-server localhost:9092
```

3. **Setup Gmail API**:
- Go to Google Cloud Console
- Enable Gmail API
- Download credentials.json
- Place in config/gmail_credentials.json

4. **Configure User Profile**:
```bash
cp config/user_profile.example.yaml config/user_profile.yaml
nano config/user_profile.yaml
```

5. **Add Your CV Template**:
```bash
cp your_cv.tex templates/cv_base.tex
```

6. **Write Motivations**:
```bash
nano data/user/motivations.md
nano data/user/experience.md
```

### Running the System

```bash
# Start Agent 1 (CV Customizer) - runs until Kafka empty
python -m src.main --agent cv

# Start Agent 2 (Cover Letter & Draft) - processes pending jobs
python -m src.main --agent cover-letter

# Or run full pipeline (sequential)
python -m src.main --full-pipeline
```

### Stopping the System

The system supports graceful and force shutdown mechanisms:

```bash
# Graceful stop - finish current job, then stop
./stop.sh

# Graceful stop (explicit)
./stop.sh --graceful

# Force stop - stop immediately (current job will resume on next start)
./stop.sh --force

# Check if agents are running
./stop.sh --status

# Using Ctrl+C (in terminal running the agents)
# First Ctrl+C:  Graceful stop (finish current job)
# Second Ctrl+C: Force stop (immediate)
```

**Graceful Shutdown Behavior:**
- Current job will complete before stopping
- Status files track exactly which stages are done
- On restart, processing resumes from incomplete jobs

**Force Shutdown Behavior:**
- Stops immediately, even mid-job
- Job folder remains with partial status
- On restart, the incomplete job will be re-processed
- No data loss - Kafka offset and job status are preserved

### Monitoring

```bash
# Check job statuses
python -m src.main --status

# View specific job
python -m src.main --view-job linkedin_12345

# Retry failed jobs
python -m src.main --retry-failed
```

### Manual Workflow

1. DroidRun publishes jobs to Kafka
2. Run CV Customizer Agent
3. Run Cover Letter Agent
4. Open Gmail, review drafts
5. Send manually after verification

---

## Profile Updater Agent (Independent)

The Profile Updater Agent runs independently from the main pipeline. It helps you manage your profile without manually editing YAML/MD files.

### Features

| Feature | Description |
|---------|-------------|
| **Initial Setup** | Provide LaTeX CVs (EN/FR) as base templates |
| **Full CV Update** | Process any format: PDF, DOCX, TXT, MD, TEX |
| **Incremental Updates** | Add certifications, skills, experience via text |
| **LaTeX Support** | Parse and update LaTeX CVs directly |
| **Template Sync** | Your templates sync to project templates |
| **Backup** | Automatic backup before any changes |

### Usage

**Initial Setup with LaTeX CVs:**
```bash
./update_profile.sh --cv-en cv_english.tex --cv-fr cv_french.tex
./update_profile.sh --cv-en cv.tex --letter-en letter.tex
```

**Full CV Update:**
```bash
./update_profile.sh --cv my_cv.pdf
./update_profile.sh --cv resume.docx
./update_profile.sh --cv cv_updated.tex
```

**Incremental Updates:**
```bash
./update_profile.sh --add "Add AWS Solutions Architect certification 2026"
./update_profile.sh --add "Add Python, Kubernetes to skills"
./update_profile.sh --add "Add new job: Senior Dev at TechCorp since 2025"
```

### Files Updated

- `config/user_profile.yaml` - Structured profile data
- `data/user/experience.md` - Experience in Markdown
- `data/user/motivations.md` - Motivations in Markdown
- `data/user/templates/*.tex` - Your LaTeX base templates
- `templates/cv_*.tex` - Project templates (synced from your base)

### Data Flow

```
Input (any of these):
├── LaTeX CV (EN/FR)      ─┐
├── PDF/DOCX/TXT CV        ├──▶ LLM Extraction ──▶ Merged Profile
├── Incremental text      ─┘                           │
                                                       ▼
                                    ┌─────────────────────────────────┐
                                    │ user_profile.yaml               │
                                    │ experience.md                   │
                                    │ motivations.md                  │
                                    │ data/user/templates/*.tex       │
                                    │ templates/cv_*.tex (synced)     │
                                    └─────────────────────────────────┘
```

---

## Troubleshooting

### Common Issues

**Kafka Connection Failed**:
- Ensure Kafka broker is running
- Check bootstrap_servers in config

**LLM Timeout**:
- Reduce max_tokens
- Check Ollama is running
- Consider using smaller model

**LaTeX Compilation Error**:
- Check LaTeX syntax in templates
- Ensure pdflatex is installed
- Check for missing packages

**Gmail API Error**:
- Re-authenticate: delete token.json
- Check API quotas
- Verify scopes in config

**Stop Script Issues**:

*"No agents are currently running" but agent is running*:
- PID file may be stale. Delete `.agent.pid` and restart
- Check if Python process is running: `ps aux | grep "src.main"`

*Graceful stop taking too long*:
- Current job (especially LLM calls) may be long-running
- Use `./stop.sh --force` if immediate stop is needed
- Check logs for current processing status

*Agent not resuming interrupted job*:
- Check `status.json` in the job folder
- Verify which stages are marked as completed
- For CV agent: job may need to be re-sent to Kafka
- For Cover Letter agent: job should auto-resume if cv_customized is complete

*Force stopped job data corrupted*:
- Check if LaTeX file is incomplete (parsing error)
- Delete the job folder and re-process from Kafka
- Status files (`status.json`) are always consistent

---

## Future Enhancements

- [ ] Web UI for monitoring
- [ ] A/B testing for cover letter styles
- [ ] Integration with more job platforms
- [ ] Automatic follow-up email scheduling
- [ ] Analytics dashboard
- [x] Resume parsing from PDF (✅ Profile Updater)
- [x] Per-agent LLM configuration (✅ Implemented)
- [x] LaTeX CV parsing (✅ Profile Updater)
- [x] Incremental profile updates (✅ Profile Updater)
- [x] Graceful and force shutdown (✅ stop.sh)
