import os
import re
import html
import base64
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText

from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

# ============================================================
# MCP SDK 2.x
# ============================================================

from mcp.server import MCPServer


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "").strip()
DEFAULT_EMAIL = os.getenv("DEFAULT_EMAIL", "").strip()

CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"

DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)


# ============================================================
# GOOGLE SCOPES
# ============================================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.send",
]


# ============================================================
# MCP SERVER
# ============================================================

mcp = MCPServer(
    "AI Study Assistant MCP"
)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_title(title):
    """
    Normalize the title.
    """

    if title is None:
        return "Study Summary"

    title = str(title).strip()

    if not title:
        return "Study Summary"

    return title


def clean_summary(summary):
    """
    Normalize summary text while preserving its content.
    """

    if summary is None:
        return ""

    return str(summary).strip()


def safe_filename(text):
    """
    Convert a title into a filesystem-safe filename.
    """

    text = clean_title(text)

    text = re.sub(
        r'[<>:"/\\|?*]',
        "_",
        text
    )

    text = re.sub(
        r"\s+",
        "_",
        text
    )

    text = text.strip("._")

    return text[:100] or "study_summary"


# ============================================================
# SUMMARY VALIDATION
# ============================================================

def validate_final_summary(summary, title=""):
    """
    Validate that the summary is actual generated content.

    This is an additional safety layer against AI agents
    accidentally passing section names, placeholders,
    retrieval instructions, or other non-summary text.
    """

    summary = clean_summary(summary)
    title = clean_title(title)

    # --------------------------------------------------------
    # Empty summary
    # --------------------------------------------------------

    if not summary:
        raise ValueError(
            "The summary is empty. "
            "You must provide the actual final summary "
            "generated from the study material."
        )

    # --------------------------------------------------------
    # Normalize for comparison
    # --------------------------------------------------------

    normalized = re.sub(
        r"\s+",
        " ",
        summary.lower()
    ).strip()

    title_normalized = re.sub(
        r"\s+",
        " ",
        title.lower()
    ).strip()

    # --------------------------------------------------------
    # Placeholder phrases
    # --------------------------------------------------------

    placeholder_phrases = [
        "summary from qdrant",
        "summary from qdrant vector store",
        "summary from qdrant_vector_store",
        "summary from qdrant vector store1",
        "retrieved documents",
        "retrieved document",
        "retrieved content",
        "retrieved information",
        "information from qdrant",
        "content from qdrant",
        "content retrieved from qdrant",
        "the information above",
        "the retrieved information",
        "the retrieved content",
        "the study material",
        "study material from qdrant",
        "section 3 of the r2-dreamer paper",
        "section 3 of the r2-dreamer",
        "section 3",
        "r2-dreamer paper",
        "generate a summary",
        "create a summary",
        "please summarize",
        "summarize the section",
        "summarize this",
        "the summary",
        "summary here",
        "summary goes here",
    ]

    # --------------------------------------------------------
    # Exact placeholder match
    # --------------------------------------------------------

    for phrase in placeholder_phrases:

        if normalized == phrase:

            raise ValueError(
                "The `summary` argument contains a placeholder "
                "or section name instead of the actual final "
                "study summary. Retrieve the study material, "
                "generate the actual summary, and call the "
                "tool again with that summary."
            )

    # --------------------------------------------------------
    # Title == Summary
    # --------------------------------------------------------

    if (
        title_normalized
        and normalized == title_normalized
    ):

        raise ValueError(
            "The `summary` argument is identical to the title. "
            "Provide the actual final summary generated from "
            "the study material."
        )

    # --------------------------------------------------------
    # Very short summary protection
    #
    # We do NOT require a huge summary.
    # But extremely short text is usually a placeholder.
    # --------------------------------------------------------

    if len(summary) < 40:

        raise ValueError(
            "The summary is too short to be a final study "
            "summary. Provide the actual summary generated "
            "from the study material."
        )

    # --------------------------------------------------------
    # Detect obvious AI tool-reference placeholders
    # --------------------------------------------------------

    suspicious_patterns = [
        r"^summary\s*[:\-]?\s*from\s+qdrant",
        r"^retrieved\s+(documents|content|information)",
        r"^content\s+from\s+qdrant",
        r"^information\s+from\s+qdrant",
        r"^result\s+from\s+qdrant",
        r"^output\s+from\s+qdrant",
        r"^use\s+qdrant",
        r"^call\s+qdrant",
    ]

    for pattern in suspicious_patterns:

        if re.search(
            pattern,
            normalized,
            re.IGNORECASE
        ):

            raise ValueError(
                "The `summary` argument appears to contain "
                "a tool instruction or retrieval placeholder "
                "instead of the actual final summary."
            )

    return summary


# ============================================================
# EMAIL VALIDATION
# ============================================================

def is_valid_email(email):
    """
    Basic email format validation.

    This does not perform DNS verification.
    """

    if not email:
        return False

    email = email.strip()

    pattern = (
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )

    return bool(
        re.match(
            pattern,
            email
        )
    )


def is_placeholder_email(email):
    """
    Detect common placeholder/example addresses
    that an AI model might accidentally generate.
    """

    if not email:
        return True

    email = email.strip().lower()

    placeholder_values = {
        "your_email@example.com",
        "you@example.com",
        "your@email.com",
        "example@example.com",
        "test@example.com",
        "user@example.com",
        "email@example.com",
        "your-email@example.com",
        "recipient@example.com",
    }

    if email in placeholder_values:
        return True

    # Reject common example domains
    if email.endswith("@example.com"):
        return True

    if email.endswith("@example.org"):
        return True

    if email.endswith("@example.net"):
        return True

    return False


def resolve_recipient(recipient):
    """
    Safely resolve the email recipient.

    Rules:

    1. Empty recipient
       -> DEFAULT_EMAIL

    2. Placeholder recipient
       -> DEFAULT_EMAIL

    3. Invalid recipient
       -> DEFAULT_EMAIL

    4. Valid explicitly provided email
       -> use that email
    """

    provided_recipient = (
        str(recipient).strip()
        if recipient
        else ""
    )

    # --------------------------------------------------------
    # No recipient supplied
    # --------------------------------------------------------

    if not provided_recipient:

        if DEFAULT_EMAIL:
            return DEFAULT_EMAIL

        return ""

    # --------------------------------------------------------
    # Placeholder
    # --------------------------------------------------------

    if is_placeholder_email(
        provided_recipient
    ):

        print(
            "WARNING: Placeholder email detected."
        )

        print(
            "Using DEFAULT_EMAIL instead."
        )

        return DEFAULT_EMAIL

    # --------------------------------------------------------
    # Invalid email
    # --------------------------------------------------------

    if not is_valid_email(
        provided_recipient
    ):

        print(
            "WARNING: Invalid recipient email detected."
        )

        print(
            "Using DEFAULT_EMAIL instead."
        )

        return DEFAULT_EMAIL

    # --------------------------------------------------------
    # Valid explicit recipient
    # --------------------------------------------------------

    return provided_recipient


# ============================================================
# GOOGLE AUTHENTICATION
# ============================================================

def get_google_credentials():
    """
    Get valid Google OAuth credentials.

    Uses token.json if available.
    Refreshes expired credentials when possible.
    Starts OAuth login if no valid credentials exist.
    """

    # --------------------------------------------------------
    # Check credentials.json
    # --------------------------------------------------------

    if not CREDENTIALS_FILE.exists():

        raise FileNotFoundError(
            "credentials.json was not found.\n"
            f"Expected location:\n{CREDENTIALS_FILE}"
        )

    credentials = None

    # --------------------------------------------------------
    # Load existing token
    # --------------------------------------------------------

    if TOKEN_FILE.exists():

        try:

            credentials = (
                Credentials
                .from_authorized_user_file(
                    str(TOKEN_FILE),
                    SCOPES
                )
            )

        except Exception as e:

            print(
                "WARNING: Could not load token.json:"
            )

            print(e)

            credentials = None

    # --------------------------------------------------------
    # Refresh expired credentials
    # --------------------------------------------------------

    if (
        credentials
        and credentials.expired
        and credentials.refresh_token
    ):

        try:

            print(
                "Refreshing Google OAuth token..."
            )

            credentials.refresh(
                Request()
            )

            TOKEN_FILE.write_text(
                credentials.to_json(),
                encoding="utf-8"
            )

            print(
                "Google OAuth token refreshed."
            )

        except Exception as e:

            print(
                "WARNING: Token refresh failed:"
            )

            print(e)

            credentials = None

    # --------------------------------------------------------
    # New OAuth login
    # --------------------------------------------------------

    if (
        not credentials
        or not credentials.valid
    ):

        print(
            "Starting Google OAuth authorization..."
        )

        flow = (
            InstalledAppFlow
            .from_client_secrets_file(
                str(CREDENTIALS_FILE),
                SCOPES
            )
        )

        credentials = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent"
        )

        TOKEN_FILE.write_text(
            credentials.to_json(),
            encoding="utf-8"
        )

        print(
            "Google OAuth authorization completed."
        )

    return credentials


# ============================================================
# TOOL 1
# GOOGLE SHEETS
# ============================================================

@mcp.tool()
def save_summary_to_google_sheets(
    title: str = "Study Summary",
    summary: str = ""
) -> str:
    """
    SAVE FINAL STUDY SUMMARY TO GOOGLE SHEETS.

    This tool performs an ACTION.
    It does NOT retrieve study material.
    It does NOT generate a summary.

    USE THIS TOOL WHEN:
    - The student asks to save a summary.
    - The student asks to store a summary.
    - The student asks to record study notes.
    - The student asks to save study notes to Google Sheets.

    REQUIRED WORKFLOW:

    Before calling this tool, the AI assistant MUST:

    1. Retrieve the relevant study material using Qdrant.
    2. Read and understand the retrieved material.
    3. Generate the FINAL study summary.
    4. Pass that exact final summary to this tool.

    IMPORTANT:

    The `summary` parameter MUST contain the actual
    complete final summary text.

    NEVER pass:
    - a section title
    - a paper title
    - "summary from Qdrant"
    - "retrieved documents"
    - "retrieved content"
    - "the information above"
    - "the study material"
    - a placeholder
    - instructions to generate a summary

    This tool does NOT create the summary.

    It only stores the summary that the AI assistant
    has already generated.

    GOOGLE SHEET COLUMNS:

    Column A = Title
    Column B = Final Summary
    Column C = Timestamp
    Column D = Source

    Return an action status after execution.

    Do not return study material as the tool result.
    """

    title = clean_title(title)

    # --------------------------------------------------------
    # Validate actual summary
    # --------------------------------------------------------

    try:

        summary = validate_final_summary(
            summary,
            title
        )

    except ValueError as e:

        print(
            "GOOGLE SHEETS VALIDATION ERROR:"
        )

        print(e)

        return (
            f"ERROR: {e}"
        )

    # --------------------------------------------------------
    # Validate spreadsheet configuration
    # --------------------------------------------------------

    if not SPREADSHEET_ID:

        return (
            "ERROR: SPREADSHEET_ID is missing "
            "from the .env file. "
            "Configure SPREADSHEET_ID before using "
            "the Google Sheets action."
        )

    try:

        print(
            "Connecting to Google Sheets..."
        )

        credentials = (
            get_google_credentials()
        )

        service = build(
            "sheets",
            "v4",
            credentials=credentials
        )

        timestamp = (
            datetime.now()
            .strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        values = [[
            title,
            summary,
            timestamp,
            "AI Study Assistant"
        ]]

        body = {
            "values": values
        }

        result = (
            service
            .spreadsheets()
            .values()
            .append(
                spreadsheetId=SPREADSHEET_ID,
                range="Sheet1!A:D",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body
            )
            .execute()
        )

        updated_range = (
            result
            .get("updates", {})
            .get(
                "updatedRange",
                "Unknown"
            )
        )

        print(
            "GOOGLE SHEETS SUCCESS!"
        )

        print(
            "Updated range:",
            updated_range
        )

        return (
            "SUCCESS: Final study summary "
            "saved to Google Sheets. "
            f"Title: {title}. "
            f"Range: {updated_range}"
        )

    except Exception as e:

        print(
            "GOOGLE SHEETS ERROR:"
        )

        print(e)

        return (
            "ERROR saving final study summary "
            f"to Google Sheets: {e}"
        )


# ============================================================
# TOOL 2
# GMAIL
# ============================================================

@mcp.tool()
def send_summary_email(
    title: str = "Study Summary",
    summary: str = "",
    recipient: str = ""
) -> str:
    """
    SEND FINAL STUDY SUMMARY BY EMAIL.

    This tool performs an ACTION only.

    USE THIS TOOL WHEN:
    - The student asks to email a summary.
    - The student asks to send a summary.
    - The student asks to send study notes.
    - The student asks to forward the final summary.

    REQUIRED WORKFLOW:

    Before calling this tool, the AI assistant MUST:

    1. Retrieve the relevant study material using Qdrant.
    2. Understand the retrieved material.
    3. Generate the FINAL study summary.
    4. Pass the EXACT SAME final summary to this tool.

    The `summary` parameter MUST contain the complete
    final study summary.

    NEVER pass:
    - "summary from Qdrant"
    - "retrieved documents"
    - "retrieved content"
    - a section title
    - a paper title
    - a placeholder
    - instructions to generate a summary

    EMAIL RECIPIENT RULE:

    Never invent an email address.

    Never use placeholder addresses such as:
    - your_email@example.com
    - you@example.com
    - test@example.com
    - example.com

    If the student does not explicitly provide another
    recipient, use the configured DEFAULT_EMAIL.

    If the model accidentally provides a placeholder or
    invalid address, the server will safely fall back
    to DEFAULT_EMAIL.

    EMAIL CONTENT:

    The email contains:
    - Title
    - Final study summary
    - Generated-by footer

    This tool sends the summary.
    It does NOT retrieve or generate study knowledge.

    Return only the email action status.
    """

    title = clean_title(title)

    # --------------------------------------------------------
    # Validate summary
    # --------------------------------------------------------

    try:

        summary = validate_final_summary(
            summary,
            title
        )

    except ValueError as e:

        print(
            "GMAIL VALIDATION ERROR:"
        )

        print(e)

        return (
            f"ERROR: {e}"
        )

    # --------------------------------------------------------
    # Resolve recipient
    # --------------------------------------------------------

    recipient = resolve_recipient(
        recipient
    )

    if not recipient:

        return (
            "ERROR: recipient email is missing "
            "and DEFAULT_EMAIL is not configured "
            "in the .env file."
        )

    # --------------------------------------------------------
    # Final validation
    # --------------------------------------------------------

    if not is_valid_email(
        recipient
    ):

        return (
            "ERROR: no valid recipient email is available. "
            "Please configure DEFAULT_EMAIL in the .env file."
        )

    try:

        print(
            "Connecting to Gmail..."
        )

        print(
            "Recipient:",
            recipient
        )

        credentials = (
            get_google_credentials()
        )

        service = build(
            "gmail",
            "v1",
            credentials=credentials
        )

        # ----------------------------------------------------
        # Email content
        # ----------------------------------------------------

        email_content = (
            f"{title}\n\n"
            f"{summary}\n\n"
            "Generated by AI Study Assistant."
        )

        message = MIMEText(
            email_content,
            "plain",
            "utf-8"
        )

        message["To"] = recipient
        message["Subject"] = title

        encoded_message = (
            base64
            .urlsafe_b64encode(
                message.as_bytes()
            )
            .decode()
        )

        result = (
            service
            .users()
            .messages()
            .send(
                userId="me",
                body={
                    "raw": encoded_message
                }
            )
            .execute()
        )

        message_id = result.get(
            "id",
            "unknown"
        )

        print(
            "GMAIL SUCCESS!"
        )

        print(
            "Message ID:",
            message_id
        )

        print(
            "Sent to:",
            recipient
        )

        return (
            "SUCCESS: Final study summary "
            f"sent to {recipient}. "
            f"Message ID: {message_id}"
        )

    except Exception as e:

        print(
            "GMAIL ERROR:"
        )

        print(e)

        return (
            "ERROR sending final study summary "
            f"by email: {e}"
        )


# ============================================================
# TOOL 3
# CREATE SUMMARY PDF
# ============================================================

@mcp.tool()
def create_summary_pdf(
    title: str = "Study Summary",
    summary: str = ""
) -> str:
    """
    CREATE A PDF FROM THE FINAL STUDY SUMMARY.

    This tool performs an ACTION.

    USE THIS TOOL WHEN:
    - The student asks to create a PDF.
    - The student asks to generate a PDF.
    - The student asks to export the summary as PDF.
    - The student asks to save study notes as PDF.

    REQUIRED WORKFLOW:

    Before calling this tool, the AI assistant MUST:

    1. Retrieve the relevant study material using Qdrant.
    2. Understand the retrieved material.
    3. Generate the FINAL study summary.
    4. Pass the EXACT final summary to this tool.

    The `summary` parameter MUST contain the complete
    final summary text.

    NEVER pass:
    - a section title
    - a paper title
    - "summary from Qdrant"
    - "retrieved documents"
    - "retrieved content"
    - a placeholder
    - an instruction to create a summary

    This tool does NOT summarize the paper.

    It only converts the already-created final summary
    into a PDF.

    Return the generated PDF path and action status.
    """

    title = clean_title(title)

    # --------------------------------------------------------
    # Validate summary
    # --------------------------------------------------------

    try:

        summary = validate_final_summary(
            summary,
            title
        )

    except ValueError as e:

        print(
            "PDF VALIDATION ERROR:"
        )

        print(e)

        return (
            f"ERROR: {e}"
        )

    try:

        # ----------------------------------------------------
        # Filename
        # ----------------------------------------------------

        filename = (
            f"{safe_filename(title)}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            ".pdf"
        )

        pdf_path = (
            DOWNLOADS_DIR /
            filename
        )

        print(
            "Creating PDF..."
        )

        print(
            "PDF path:",
            pdf_path
        )

        # ----------------------------------------------------
        # PDF document
        # ----------------------------------------------------

        document = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm
        )

        styles = (
            getSampleStyleSheet()
        )

        # ----------------------------------------------------
        # Title style
        # ----------------------------------------------------

        title_style = ParagraphStyle(
            "StudyTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            alignment=TA_LEFT,
            spaceAfter=20
        )

        # ----------------------------------------------------
        # Body style
        # ----------------------------------------------------

        body_style = ParagraphStyle(
            "StudyBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=16,
            alignment=TA_LEFT,
            spaceAfter=8
        )

        story = []

        # ----------------------------------------------------
        # Title
        # ----------------------------------------------------

        story.append(
            Paragraph(
                html.escape(title),
                title_style
            )
        )

        story.append(
            Spacer(
                1,
                0.3 * cm
            )
        )

        # ----------------------------------------------------
        # Summary content
        # ----------------------------------------------------

        for line in summary.splitlines():

            line = line.strip()

            # Empty line
            if not line:

                story.append(
                    Spacer(
                        1,
                        0.15 * cm
                    )
                )

                continue

            # ------------------------------------------------
            # Basic markdown support
            # ------------------------------------------------

            line = re.sub(
                r"\*\*(.*?)\*\*",
                r"<b>\1</b>",
                line
            )

            line = re.sub(
                r"\*(.*?)\*",
                r"<i>\1</i>",
                line
            )

            # ------------------------------------------------
            # Protect basic formatting tags
            # ------------------------------------------------

            placeholders = {}

            def protect_tag(match):

                key = (
                    f"___TAG_"
                    f"{len(placeholders)}___"
                )

                placeholders[key] = (
                    match.group(0)
                )

                return key

            line = re.sub(
                r"</?b>|</?i>",
                protect_tag,
                line
            )

            # ------------------------------------------------
            # Escape HTML
            # ------------------------------------------------

            line = html.escape(
                line
            )

            # ------------------------------------------------
            # Restore formatting tags
            # ------------------------------------------------

            for key, value in (
                placeholders.items()
            ):

                line = line.replace(
                    key,
                    value
                )

            story.append(
                Paragraph(
                    line,
                    body_style
                )
            )

        # ----------------------------------------------------
        # Footer
        # ----------------------------------------------------

        story.append(
            Spacer(
                1,
                0.5 * cm
            )
        )

        generated_at = (
            datetime.now()
            .strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        story.append(
            Paragraph(
                f"Generated: {generated_at}",
                styles["Normal"]
            )
        )

        # ----------------------------------------------------
        # Build PDF
        # ----------------------------------------------------

        document.build(
            story
        )

        print(
            "PDF SUCCESS!"
        )

        print(
            "Saved:",
            pdf_path
        )

        return (
            "SUCCESS: PDF created successfully. "
            f"File: {pdf_path}"
        )

    except Exception as e:

        print(
            "PDF ERROR:"
        )

        print(e)

        return (
            "ERROR creating PDF: "
            f"{e}"
        )


# ============================================================
# SERVER STARTUP
# ============================================================

if __name__ == "__main__":

    print("=" * 60)

    print(
        "AI Study Assistant MCP Server"
    )

    print("=" * 60)

    print(
        "Base directory:"
    )

    print(
        BASE_DIR
    )

    print(
        "Spreadsheet configured:"
    )

    print(
        bool(SPREADSHEET_ID)
    )

    print(
        "Default email:"
    )

    print(
        DEFAULT_EMAIL
    )

    print(
        "Credentials file:"
    )

    print(
        CREDENTIALS_FILE
    )

    print(
        "Token file:"
    )

    print(
        TOKEN_FILE
    )

    print(
        "Downloads directory:"
    )

    print(
        DOWNLOADS_DIR
    )

    print(
        "MCP endpoint:"
    )

    print(
        "http://127.0.0.1:8000/mcp"
    )

    print("=" * 60)

    print(
        "Available MCP tools:"
    )

    print(
        "1. save_summary_to_google_sheets"
    )

    print(
        "2. send_summary_email"
    )

    print(
        "3. create_summary_pdf"
    )

    print("=" * 60)

    # --------------------------------------------------------
    # Start MCP server
    # --------------------------------------------------------

    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8000
    )