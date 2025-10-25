import re
from typing import Any, Callable
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from yt_dlp import YoutubeDL
from pydantic import BaseModel, Field


class Tools:
    class UserValves(BaseModel):
        TRANSCRIPT_LANGUAGE: str = Field(
            default="en,en_auto,de,de_auto",
            description="Preferred transcript languages, comma-separated (e.g. 'en,en_auto')",
        )
        TRANSCRIPT_TRANSLATE: str = Field(
            default="en",
            description="Target translation language",
        )
        GET_VIDEO_DETAILS: bool = Field(
            default=True,
            description="Include video title and uploader in the output",
        )

    async def get_youtube_transcript(
        self,
        url: str,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Retrieves YouTube video details and transcripts with optional translation
        :param url: YouTube video URL
        :return: Details and transcripts
        """

        async def emit(description, status="in_progress", done=False):
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {
                            "status": status,
                            "description": description,
                            "done": done,
                        },
                    }
                )

        valves = __user__.get("valves", self.UserValves())

        try:
            await emit("Validating YouTube URL")
            if not url:
                raise ValueError("No YouTube URL provided")

            match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
            if not match:
                raise ValueError("Couldn't extract video ID")
            video_id = match.group(1)

            title = author = ""
            if valves.GET_VIDEO_DETAILS:
                await emit("Fetching details")
                try:
                    with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                        info = ydl.extract_info(url, download=False)
                        title, author = info.get("title", ""), info.get("uploader", "")
                except Exception as e:
                    await emit(f"Could not fetch details: {e}")

            await emit("Fetching transcript")
            langs = [lang.strip() for lang in valves.TRANSCRIPT_LANGUAGE.split(",")]

            ytt_api = YouTubeTranscriptApi()
            transcript_list = ytt_api.list(video_id)
            transcript_obj = transcript_list.find_transcript(langs)

            if (
                valves.TRANSCRIPT_TRANSLATE
                and transcript_obj.language_code not in langs
            ):
                transcript_obj = transcript_obj.translate(valves.TRANSCRIPT_TRANSLATE)

            fetched = transcript_obj.fetch()
            transcript_text = "\n".join(
                [entry["text"] for entry in fetched.to_raw_data()]
            )

            if title and author:
                transcript_text = f"{title}\nby {author}\n\n{transcript_text}"

            await emit(f"Transcript retrieved", "success", True)
            return transcript_text

        except (TranscriptsDisabled, NoTranscriptFound, Exception) as e:
            msg = f"Error: {e}"
            await emit(msg, "error", True)
            return msg
