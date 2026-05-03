"""PDF text extraction tool for StoryTeller — supports local files and S3."""

import os
import tempfile
import boto3
import pdfplumber
from strands import tool

UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-west-2"))


def _resolve_file(file_path: str) -> str:
    """Download from S3 if path starts with s3:// or uploads/, otherwise return as-is."""
    s3_key = None

    if file_path.startswith("s3://"):
        # Could be s3://bucket/key or s3://key (assume our bucket)
        path = file_path[5:]
        if path.startswith(UPLOAD_BUCKET + "/"):
            s3_key = path[len(UPLOAD_BUCKET) + 1:]
        elif path.startswith("uploads/"):
            s3_key = path
        else:
            # Try stripping bucket name
            parts = path.split("/", 1)
            s3_key = parts[1] if len(parts) > 1 else path

    elif file_path.startswith("uploads/"):
        s3_key = file_path

    if s3_key and UPLOAD_BUCKET:
        # Download to temp file
        suffix = os.path.splitext(s3_key)[1] or ".pdf"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            s3.download_file(UPLOAD_BUCKET, s3_key, tmp.name)
            return tmp.name
        except Exception as e:
            raise FileNotFoundError(f"Failed to download s3://{UPLOAD_BUCKET}/{s3_key}: {e}")

    return file_path


@tool
def pdf_extract(file_path: str) -> str:
    """Extract text from a PDF file using pdfplumber.

    Use this tool when the user provides a PDF file or uploads a PDF.
    Supports local paths and S3 references (s3://... or uploads/...).

    Args:
        file_path: Path to the PDF file — local path or S3 key (s3://bucket/key or uploads/email/session/file.pdf).

    Returns:
        Concatenated text from all pages of the PDF.
    """
    local_path = None
    try:
        local_path = _resolve_file(file_path)
        pages_text = []
        with pdfplumber.open(local_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    pages_text.append(f"--- Page {i} ---\n{text}")

        if not pages_text:
            return f"[Warning] No text could be extracted from {file_path}. The PDF may contain only images."

        return f"PDF content ({len(pages_text)} pages):\n\n" + "\n\n".join(pages_text)

    except FileNotFoundError as e:
        return f"[Error] PDF file not found: {e}"
    except Exception as e:
        return f"[Error] Failed to extract PDF: {str(e)}"
    finally:
        # Cleanup temp file if we downloaded from S3
        if local_path and local_path != file_path and os.path.exists(local_path):
            os.unlink(local_path)
