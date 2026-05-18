"""StoryTeller agent tools package."""

from .content_fetch import content_fetch
from .pdf_extract import pdf_extract
from .pptx_extract import pptx_extract
from .web_research import web_research
from .trend_analysis import trend_analysis
from .generate_thumbnail import make_generate_thumbnail_tool
from .save_user_photo import make_save_user_photo_tool
from .list_style_templates import list_style_templates
from .list_user_photos import make_list_user_photos_tool
from .start_transcription import make_start_transcription_tool
from .list_pending_jobs import make_list_pending_jobs_tool
from .mark_job_consumed import make_mark_job_consumed_tool
from .read_file import make_read_file_tool
from .analyze_youtube_video import analyze_youtube_video

__all__ = [
    "content_fetch",
    "pdf_extract",
    "pptx_extract",
    "web_research",
    "trend_analysis",
    "make_generate_thumbnail_tool",
    "make_save_user_photo_tool",
    "list_style_templates",
    "make_list_user_photos_tool",
    "make_start_transcription_tool",
    "make_list_pending_jobs_tool",
    "make_mark_job_consumed_tool",
    "make_read_file_tool",
    "analyze_youtube_video",
]
