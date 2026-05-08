"""Markdown document export tool for StoryTeller.

Generates a video plan document, uploads to S3, and returns a download link.
"""

import os
import uuid
import boto3
from datetime import datetime, timezone
from strands import tool

UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "storyteller-sessions")
REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))

s3 = boto3.client("s3", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)


def make_export_document_tool(email: str, session_id: str):
    """Create an export_document tool pre-bound with email and session_id."""

    @tool
    def export_document(
        title: str,
        video_type: str,
        duration_estimate: str,
        hook: str,
        sections: str,
        thumbnail_suggestion: str,
        seo_tags_hebrew: str,
        seo_tags_english: str,
        chapter_timestamps: str = "",
        series_info: str = "",
    ) -> str:
        """Generate a clean markdown document with the complete video plan and upload it.

        Use this tool when the video plan is finalized and the user wants the output
        as a structured document. All content should be in Hebrew.
        The document will be uploaded and a download link returned to the user.

        Args:
            title: Video title in Hebrew.
            video_type: Type of video (e.g., "tutorial", "news roundup", "builder story").
            duration_estimate: Estimated duration (e.g., "5:30").
            hook: The hook/opening text in Hebrew.
            sections: The full outline or script content in Hebrew (markdown formatted).
            thumbnail_suggestion: Description of suggested thumbnail concept in Hebrew.
            seo_tags_hebrew: Comma-separated Hebrew tags.
            seo_tags_english: Comma-separated English tags.
            chapter_timestamps: Optional chapter timestamps for YouTube description.
            series_info: Optional series context if this is part of a series.

        Returns:
            Confirmation with download link for the generated document.
        """
        # Build document
        doc_parts = []
        doc_parts.append(f"# {title}")
        doc_parts.append("")

        if series_info:
            doc_parts.append(f"> **סדרה:** {series_info}")
            doc_parts.append("")

        doc_parts.append(f"**סוג וידאו:** {video_type}")
        doc_parts.append(f"**משך משוער:** {duration_estimate}")
        doc_parts.append("")

        doc_parts.append("## הוק (פתיחה)")
        doc_parts.append("")
        doc_parts.append(hook)
        doc_parts.append("")

        doc_parts.append("## מבנה הוידאו")
        doc_parts.append("")
        doc_parts.append(sections)
        doc_parts.append("")

        if chapter_timestamps:
            doc_parts.append("## חותמות זמן לתיאור (Chapters)")
            doc_parts.append("")
            doc_parts.append(chapter_timestamps)
            doc_parts.append("")

        doc_parts.append("## תמונה ממוזערת (Thumbnail)")
        doc_parts.append("")
        doc_parts.append(thumbnail_suggestion)
        doc_parts.append("")

        doc_parts.append("## תגיות SEO")
        doc_parts.append("")
        doc_parts.append(f"**עברית:** {seo_tags_hebrew}")
        doc_parts.append(f"**English:** {seo_tags_english}")
        doc_parts.append("")

        doc_parts.append("---")
        doc_parts.append("*נוצר על ידי StoryTeller — כלי תכנון וידאו מבוסס AI*")

        document = "\n".join(doc_parts)

        # Upload to S3
        file_id = str(uuid.uuid4())[:8]
        # Clean title for filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title).strip()[:50]
        filename = f"{safe_title or 'video-plan'}.md"
        s3_key = f"uploads/{email}/{session_id}/{file_id}-{filename}"

        try:
            s3.put_object(
                Bucket=UPLOAD_BUCKET,
                Key=s3_key,
                Body=document.encode("utf-8"),
                ContentType="text/markdown; charset=utf-8",
                ContentDisposition=f'attachment; filename="{filename}"',
            )

            # Track file in session record
            now = datetime.now(timezone.utc).isoformat()
            table = dynamodb.Table(SESSIONS_TABLE)
            try:
                table.update_item(
                    Key={"email": email, "session_id": session_id},
                    UpdateExpression="SET #f = list_append(if_not_exists(#f, :empty), :file), updated_at = :now",
                    ExpressionAttributeNames={"#f": "files"},
                    ExpressionAttributeValues={
                        ":file": [{
                            "file_id": file_id,
                            "filename": filename,
                            "s3_key": s3_key,
                            "content_type": "text/markdown",
                            "uploaded_at": now,
                        }],
                        ":empty": [],
                        ":now": now,
                    },
                )
            except Exception:
                pass  # Best effort — file is in S3 regardless

            # Return a file:// reference — frontend resolves on-demand
            return f"\u2705 המסמך נוצר בהצלחה!\n\n[\ud83d\udcc4 {filename}](file://{file_id})"

        except Exception as e:
            # Fallback — return the document as text if upload fails
            return f"⚠️ לא הצלחתי להעלות את המסמך, אבל הנה התוכן:\n\n{document}"

    return export_document
