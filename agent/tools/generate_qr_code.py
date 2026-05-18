"""QR code generation tool for StoryTeller.

Uses AgentCore Code Interpreter to generate QR code images, then
uploads them to S3 and returns inline media:// references.
"""

import base64
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from ipaddress import ip_address
from urllib.parse import urlparse

import boto3
from strands import tool

logger = logging.getLogger(__name__)

UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "storyteller-sessions")
REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))

s3 = boto3.client("s3", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)

# Private IP ranges to reject
_PRIVATE_RANGES = re.compile(
    r"^(10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|127\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|169\.254\.\d{1,3}\.\d{1,3})$"
)


def sanitize_url(url: str) -> str | None:
    """Validate and sanitize a URL. Returns cleaned URL or None if invalid."""
    if not url or not url.strip():
        return None
    url = url.strip()
    if len(url) > 2048:
        return None

    # Block dangerous schemes
    lower = url.lower()
    if lower.startswith("javascript:") or lower.startswith("data:"):
        return None

    # Must be http or https
    if not (lower.startswith("http://") or lower.startswith("https://")):
        return None

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    hostname = parsed.hostname
    if not hostname:
        return None

    # Check for private IPs
    try:
        addr = ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            return None
    except ValueError:
        # Not an IP — that's fine, it's a domain
        pass

    # Also reject hostnames that look like private IPs
    if _PRIVATE_RANGES.match(hostname):
        return None

    return url


def make_generate_qr_code_tool(email: str, session_id: str):
    """Create a generate_qr_code tool pre-bound with email and session_id."""

    @tool
    def generate_qr_code(urls: list[str]) -> str:
        """Generate QR code images for one or more URLs.

        Creates high-quality QR code PNG images that can be scanned with any
        QR reader. Each URL gets its own QR code image.

        Args:
            urls: List of URLs to encode as QR codes (e.g. ["https://example.com"]).

        Returns:
            Markdown with inline image references for each generated QR code.
        """
        if not urls:
            return "❌ No URLs provided. Please provide at least one URL."

        # Sanitize all URLs first
        clean_urls: list[str] = []
        errors: list[str] = []
        for url in urls:
            cleaned = sanitize_url(url)
            if cleaned:
                clean_urls.append(cleaned)
            else:
                errors.append(f"- `{url}`: invalid or blocked URL")

        if not clean_urls:
            return "❌ All provided URLs are invalid:\n" + "\n".join(errors)

        # Generate QR codes using Code Interpreter
        try:
            from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

            ci = CodeInterpreter(region=REGION)
            ci.start()
        except Exception as e:
            logger.error("Failed to start Code Interpreter session: %s", e)
            return f"❌ Failed to start Code Interpreter: {e}"

        results: list[dict] = []
        try:
            # Build Python code to generate all QR codes in one execution
            urls_repr = repr(clean_urls)
            code = f"""
import qrcode
import base64
import io
import json

urls = {urls_repr}
output = []
for url in urls:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    output.append({{"url": url, "b64": b64}})

print("__QR_RESULT__" + json.dumps(output))
"""

            # Execute in Code Interpreter
            response = ci.execute_code(code)

            # Parse the streaming response — collect all output text
            output_text = ""
            if isinstance(response, dict) and "stream" in response:
                for event in response["stream"]:
                    if "result" in event:
                        result = event["result"]
                        if "content" in result:
                            for content_item in result["content"]:
                                if "text" in content_item:
                                    output_text += content_item["text"]
                                elif "type" in content_item and content_item["type"] == "text":
                                    output_text += content_item.get("data", "")
            elif isinstance(response, dict):
                # Non-streaming fallback
                output_text = str(response)
            elif isinstance(response, str):
                output_text = response

            # Extract the JSON result
            marker = "__QR_RESULT__"
            if marker not in output_text:
                logger.error("Code Interpreter output missing marker: %s", output_text[:500])
                return f"❌ Code Interpreter failed to generate QR codes. Output: {output_text[:200]}"

            json_str = output_text.split(marker, 1)[1].strip()
            # Handle potential trailing output
            if "\n" in json_str:
                json_str = json_str.split("\n")[0]
            qr_data = __import__("json").loads(json_str)

            # Upload each QR code to S3
            now = datetime.now(timezone.utc).isoformat()
            for item in qr_data:
                url = item["url"]
                png_bytes = base64.b64decode(item["b64"])
                filename = f"qrcode-{uuid.uuid4().hex[:8]}.png"
                file_id = filename  # flat id (no slashes) — safe for API Gateway path params
                s3_key = f"media/qrcodes/{email}/{session_id}/{filename}"

                try:
                    s3.put_object(
                        Bucket=UPLOAD_BUCKET,
                        Key=s3_key,
                        Body=png_bytes,
                        ContentType="image/png",
                    )
                    results.append({
                        "url": url,
                        "file_id": file_id,
                        "filename": filename,
                        "s3_key": s3_key,
                        "size_bytes": len(png_bytes),
                    })
                except Exception as e:
                    logger.error("S3 upload failed for %s: %s", url, e)
                    errors.append(f"- `{url}`: S3 upload failed — {e}")

        except Exception as e:
            logger.error("Code Interpreter execution failed: %s", e)
            return f"❌ QR code generation failed: {e}"
        finally:
            try:
                ci.stop()
            except Exception:
                pass

        if not results:
            return "❌ Failed to generate any QR codes:\n" + "\n".join(errors)

        # Register files in the sessions table
        try:
            now = datetime.now(timezone.utc).isoformat()
            table = dynamodb.Table(SESSIONS_TABLE)
            file_records = [
                {
                    "file_id": r["file_id"],
                    "filename": r["filename"],
                    "s3_key": r["s3_key"],
                    "content_type": "image/png",
                    "uploaded_at": now,
                }
                for r in results
            ]
            table.update_item(
                Key={"email": email, "session_id": session_id},
                UpdateExpression="SET #f = list_append(if_not_exists(#f, :empty), :files), updated_at = :now",
                ExpressionAttributeNames={"#f": "files"},
                ExpressionAttributeValues={
                    ":files": file_records,
                    ":empty": [],
                    ":now": now,
                },
            )
        except Exception as e:
            logger.warning("Failed to register files in session: %s", e)

        # Build markdown response
        parts: list[str] = []
        for r in results:
            parts.append(f"![QR Code for {r['url']}](media://{r['file_id']})")

        if errors:
            parts.append("\n⚠️ Some URLs failed:")
            parts.extend(errors)

        return "\n\n".join(parts)

    return generate_qr_code
