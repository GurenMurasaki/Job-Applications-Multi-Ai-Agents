"""
Gmail Service

Handles Gmail API integration for creating drafts with attachments.
"""

import base64
import mimetypes
import os
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List, Dict, Any
from loguru import logger


class GmailService:
    """
    Service for Gmail API operations.
    
    Creates drafts with CV and cover letter attachments.
    """
    
    def __init__(self, config: dict):
        """
        Initialize the Gmail service.
        
        Args:
            config: Gmail configuration dictionary
        """
        self.credentials_file = Path(config.get("credentials_file", "config/gmail_credentials.json"))
        self.token_file = Path(config.get("token_file", "config/gmail_token.json"))
        self.scopes = config.get("scopes", [
            "https://www.googleapis.com/auth/gmail.compose",
            "https://www.googleapis.com/auth/gmail.modify"
        ])
        
        self._service = None
        self._authenticated = False
    
    def _authenticate(self) -> bool:
        """Authenticate with Gmail API."""
        if self._authenticated:
            return True
        
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except ImportError:
            logger.error("Google API libraries not installed")
            return False
        
        creds = None
        
        # Load existing token
        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_file), self.scopes)
            except Exception as e:
                logger.warning(f"Could not load token: {e}")
        
        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Could not refresh token: {e}")
                    creds = None
            
            if not creds:
                if not self.credentials_file.exists():
                    logger.error(f"Gmail credentials file not found: {self.credentials_file}")
                    return False
                
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_file), self.scopes
                    )
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"Authentication failed: {e}")
                    return False
            
            # Save token
            try:
                self.token_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_file, "w") as token:
                    token.write(creds.to_json())
            except Exception as e:
                logger.warning(f"Could not save token: {e}")
        
        try:
            self._service = build("gmail", "v1", credentials=creds)
            self._authenticated = True
            logger.info("Gmail API authenticated successfully")
            return True
        except Exception as e:
            logger.error(f"Could not build Gmail service: {e}")
            return False
    
    def create_draft(self, to: str, subject: str, body: str, 
                     attachments: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
        """
        Create a Gmail draft with attachments.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body text
            attachments: List of dicts with 'path' and 'filename' keys
            
        Returns:
            Draft ID if successful, None otherwise
        """
        if not self._authenticate():
            logger.error("Gmail authentication failed")
            return None
        
        try:
            # Create message
            message = self._create_message(to, subject, body, attachments)
            
            # Create draft
            draft = self._service.users().drafts().create(
                userId="me",
                body={"message": message}
            ).execute()
            
            draft_id = draft.get("id")
            logger.info(f"Draft created with ID: {draft_id}")
            return draft_id
            
        except Exception as e:
            logger.error(f"Failed to create draft: {e}")
            return None
    
    def _create_message(self, to: str, subject: str, body: str,
                        attachments: Optional[List[Dict[str, str]]] = None) -> Dict[str, str]:
        """Create email message with optional attachments."""
        if attachments:
            message = MIMEMultipart()
            message["to"] = to
            message["subject"] = subject
            message.attach(MIMEText(body, "plain"))
            
            for attachment in attachments:
                self._add_attachment(message, attachment)
        else:
            message = MIMEText(body)
            message["to"] = to
            message["subject"] = subject
        
        # Encode message
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        return {"raw": raw}
    
    def _add_attachment(self, message: MIMEMultipart, attachment: Dict[str, str]):
        """Add an attachment to the message."""
        file_path = Path(attachment["path"])
        filename = attachment.get("filename", file_path.name)
        
        if not file_path.exists():
            logger.warning(f"Attachment file not found: {file_path}")
            return
        
        # Guess MIME type
        content_type, encoding = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"
        
        main_type, sub_type = content_type.split("/", 1)
        
        try:
            with open(file_path, "rb") as f:
                file_data = f.read()
            
            mime_attachment = MIMEBase(main_type, sub_type)
            mime_attachment.set_payload(file_data)
            encoders.encode_base64(mime_attachment)
            
            mime_attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=filename
            )
            
            message.attach(mime_attachment)
            logger.debug(f"Added attachment: {filename}")
            
        except Exception as e:
            logger.error(f"Failed to add attachment {filename}: {e}")
    
    def list_drafts(self, max_results: int = 10) -> List[Dict[str, Any]]:
        """List existing drafts."""
        if not self._authenticate():
            return []
        
        try:
            results = self._service.users().drafts().list(
                userId="me",
                maxResults=max_results
            ).execute()
            
            return results.get("drafts", [])
        except Exception as e:
            logger.error(f"Failed to list drafts: {e}")
            return []
    
    def delete_draft(self, draft_id: str) -> bool:
        """Delete a draft by ID."""
        if not self._authenticate():
            return False
        
        try:
            self._service.users().drafts().delete(
                userId="me",
                id=draft_id
            ).execute()
            logger.info(f"Deleted draft: {draft_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete draft: {e}")
            return False
