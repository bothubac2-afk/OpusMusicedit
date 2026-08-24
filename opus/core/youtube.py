import os
import re
import aiohttp
import asyncio

from py_yt import Playlist, VideosSearch
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from typing import Union

from opus import logger
from opus.helpers import Track, utils

# Saavn — Song *naam* se search karta hai (video ID se nahi), isliye sirf
# tab kaam karta hai jab humare paas title ho (search se aaye Track, ya
# URL-based request mein yt-dlp se mila title). Koi API key ya proxy nahi
# chahiye.
SAAVN_API = "https://saavn-api-eight.vercel.app"

DOWNLOAD_DIR = "downloads"


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="

        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)"
        )

    # ── Core Methods ──────────────────────────────────────────

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def search(self, query: str, m_id: int, video=False):
        try:
            search = VideosSearch(query, limit=1)
            results = await search.next()
        except Exception as e:
            logger.error(f"Search Error: {e}")
            return None

        if results and results.get("result"):
            data = results["result"][0]
            return Track(
                id=data.get("id"),
                channel_name=data.get("channel", {}).get("name"),
                duration=data.get("duration"),
                duration_sec=utils.to_seconds(data.get("duration")),
                message_id=m_id,
                title=data.get("title")[:25],
                thumbnail=data.get("thumbnails", [{}])[-1]["url"].split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short"),
                video=video,
            )

    async def playlist(self, limit, user, url, video):
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist["videos"][:limit]:
                tracks.append(
                    Track(
                        id=data.get("id"),
                        channel_name=data.get("channel", {}).get("name"),
                        duration=data.get("duration"),
                        duration_sec=utils.to_seconds(data.get("duration")),
                        title=data.get("title")[:25],
                        thumbnail=data.get("thumbnails")[-1]["url"].split("?")[0],
                        url=data.get("link").split("&list=")[0],
                        user=user,
                        view_count="",
                        video=video,
                    )
                )
        except Exception as e:
            logger.error(f"Playlist Error: {e}")
        return tracks

    async def url(self, message_1: Message):
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)

        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset: entity.offset + entity.length]
        return None

    # ── Download Methods ──────────────────────────────────────

    async def saavn_download(self, title: str, video_id: str):
        """
        Song naam se JioSaavn pe search karta hai aur audio download karta
        hai. Video download nahi karta (Saavn sirf audio deta hai).
        """
        if not title:
            logger.warning("[Saavn] Title nahi mila, skip.")
            return None

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: naam se search
                async with session.get(
                    f"{SAAVN_API}/api/search/songs",
                    params={"query": title, "limit": 1},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"[Saavn] Search status: {resp.status}")
                        return None
                    data = await resp.json()

                results = (
                    data.get("data", {}).get("results", [])
                    if isinstance(data, dict)
                    else []
                )
                if not results:
                    logger.warning(f"[Saavn] Koi result nahi mila: {title}")
                    return None

                song = results[0]
                download_urls = song.get("downloadUrl", [])
                if not download_urls:
                    logger.warning("[Saavn] downloadUrl missing in response.")
                    return None

                # Sabse high quality wala link (list ke aakhir mein hota hai)
                stream_url = download_urls[-1].get("url")
                if not stream_url:
                    return None

                # Step 2: stream download karke file mein save
                os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                filename = f"{DOWNLOAD_DIR}/{video_id}.mp3"

                async with session.get(
                    stream_url, timeout=aiohttp.ClientTimeout(total=60, connect=5)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"[Saavn] Stream status: {resp.status}")
                        return None
                    with open(filename, "wb") as f:
                        async for chunk in resp.content.iter_chunked(131072):
                            f.write(chunk)

            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                logger.info(f"[Saavn] Download success ✓ ({title})")
                return filename

            logger.warning("[Saavn] Empty file!")
        except Exception as e:
            logger.warning(f"[Saavn] Error: {e}")

        return None

    async def download(self, video_id: str, video: bool = False, title: str = None):
        if video:
            logger.warning("[Saavn] Video download supported nahi hai (audio-only API).")
            return None

        return await self.saavn_download(title, video_id)
        
