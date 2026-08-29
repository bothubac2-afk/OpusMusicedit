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

# OpusApi — humara khud ka self-hosted yt-dlp based API. Video ID/URL se
# seedha download karta hai, proxy rotation + caching ke saath. Primary
# provider — koi API key nahi chahiye, bas token-based two-step flow hai.
OPUSAPI_BASE = "https://opusmusicapi-nf2e.onrender.com"

# Saavn — Song *naam* se search karta hai (video ID se nahi), isliye sirf
# tab kaam karta hai jab humare paas title ho (search se aaye Track, ya
# URL-based request mein yt-dlp se mila title). Koi API key ya proxy nahi
# chahiye. Fallback jab OpusApi fail ho jaaye.
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

    async def opusapi_download(self, video_id: str, video: bool = False):
        """
        OpusApi (self-hosted) se download karta hai — video ID se seedha,
        naam ki zaroorat nahi. Do-step flow: pehle token lo, phir stream
        karo. Server-side yt-dlp + proxy rotation + caching already hai,
        isliye pehli baar thoda time lag sakta hai, cache-hit pe fast.
        """
        media_type = "video" if video else "audio"

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: download token lo
                async with session.get(
                    f"{OPUSAPI_BASE}/download",
                    params={"url": video_id, "type": media_type},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"[OpusApi] Token status: {resp.status}")
                        return None
                    data = await resp.json()
                    token = data.get("download_token")
                    if not token:
                        logger.warning("[OpusApi] Token missing in response.")
                        return None

                # Step 2: token se actual file stream karo
                # (fresh video pe server-side download hota hai, isliye
                # generous timeout — cache-hit pe turant aa jaata hai)
                async with session.get(
                    f"{OPUSAPI_BASE}/stream/{video_id}",
                    params={"type": media_type, "token": token},
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"[OpusApi] Stream status: {resp.status}")
                        return None

                    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                    ext = "mp4" if video else "m4a"
                    filename = f"{DOWNLOAD_DIR}/{video_id}.{ext}"

                    with open(filename, "wb") as f:
                        async for chunk in resp.content.iter_chunked(131072):
                            f.write(chunk)

            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                logger.info(f"[OpusApi] Download success ✓ ({video_id})")
                return filename

            logger.warning("[OpusApi] Empty file!")
        except Exception as e:
            logger.warning(f"[OpusApi] Error: {e}")

        return None

    async def saavn_download(self, title: str, video_id: str):
        """
        Song naam se JioSaavn pe search karta hai aur audio download karta
        hai. Video download nahi karta (Saavn sirf audio deta hai).
        Fallback — jab OpusApi fail ho jaaye tab use hota hai.
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
        # Primary: OpusApi (self-hosted, video ID se seedha download,
        # video support bhi hai)
        result = await self.opusapi_download(video_id, video=video)
        if result:
            return result

        # Fallback: Saavn (sirf audio, naam se search)
        if video:
            logger.warning("[Saavn] Video download supported nahi hai (audio-only API).")
            return None

        logger.info("[OpusApi] Fail hua, Saavn try kar rahe hain...")
        return await self.saavn_download(title, video_id)
                    
