import os
import re
import time
import yt_dlp
import random
import asyncio
import aiohttp

from py_yt import Playlist, VideosSearch
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from typing import Union

from opus import logger
from opus.helpers import Track, utils

# ── IG-YT Download API (primary) ────────────────────────────────
# video_id se YouTube URL banake bhejte hain (?q=<youtube_url>), response
# JSON mein "media[0].url" / "primaryUrl" ke andar actual downloadable file
# link hota hai — usko phir stream/download karte hain. Koi API key nahi
# chahiye.
IGYT_API = {
    "url": "https://ig-yt-download-api.vercel.app",
    "video_endpoint": "/api/download",
    "audio_endpoint": "/api/MP3/download",
}

# Saavn — sabse aakhri fallback. Song *naam* se search karta hai (video ID se
# nahi), isliye sirf tab kaam karta hai jab humare paas title ho (search se
# aaye Track, ya URL-based request mein yt-dlp se mila title). YouTube ke
# rate-limit/block wali windows mein temporary safety net ki tarah use hota
# hai — proxy/cookie/Deno kuch nahi chahiye.
SAAVN_API = "https://saavn-api-eight.vercel.app"

IGYT_FAIL_THRESHOLD = 3
IGYT_BLOCK_DURATION = 2 * 3600  # 2 hours — free vercel API, halka block rakha
# ─────────────────────────────────────────────────────────────

DOWNLOAD_DIR = "downloads"


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="

        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)"
        )

        self.cookies = []
        self.checked = False
        self.cookie_dir = "opus/cookies"

        # IG-YT API ke liye circuit breaker (single API hai, key ki
        # zaroorat nahi)
        self._igyt_fail_count = 0
        self._igyt_blocked_until = 0

    def get_cookies(self):
        """
        Cookie files load karta hai, lekin sirf wahi jo valid Netscape
        format mein hon. Corrupt/empty/wrong-format file ko yahin skip
        kar dete hain taaki yt-dlp ke andar cookiejar load/save crash
        na kare aur poora download() chain na toote.
        """
        if not self.checked:
            if os.path.exists(self.cookie_dir):
                for file in os.listdir(self.cookie_dir):
                    if file.endswith(".txt"):
                        path = f"{self.cookie_dir}/{file}"
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                first_line = f.readline()
                            if first_line.startswith("# Netscape") or first_line.startswith(
                                "# HTTP Cookie"
                            ):
                                self.cookies.append(path)
                            else:
                                logger.warning(
                                    f"Skipping invalid cookie file (bad header): {path}"
                                )
                        except Exception as e:
                            logger.warning(f"Cookie read error {path}: {e}")
            self.checked = True
        return random.choice(self.cookies) if self.cookies else None

    # ── IG-YT API ke liye circuit breaker ──────────────────────

    def _igyt_is_blocked(self) -> bool:
        now = time.time()
        if now < self._igyt_blocked_until:
            remaining = int((self._igyt_blocked_until - now) / 60)
            logger.info(f"[IGYT] Blocked! ~{remaining}min remaining.")
            return True
        if self._igyt_fail_count >= IGYT_FAIL_THRESHOLD:
            logger.info("[IGYT] Block khatam, phir se try karega.")
            self._igyt_fail_count = 0
        return False

    def _igyt_mark_fail(self):
        self._igyt_fail_count += 1
        logger.warning(
            f"[IGYT] Fail count: {self._igyt_fail_count}/{IGYT_FAIL_THRESHOLD}"
        )
        if self._igyt_fail_count >= IGYT_FAIL_THRESHOLD:
            self._igyt_blocked_until = time.time() + IGYT_BLOCK_DURATION
            logger.warning("[IGYT] Blocked for 2 hours!")

    def _igyt_mark_success(self):
        self._igyt_fail_count = 0
        self._igyt_blocked_until = 0
        logger.info("[IGYT] Success! Fail count reset.")

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

    async def igyt_download(self, video_id: str, video: bool = False):
        """
        Primary download source. ig-yt-download-api.vercel.app ko YouTube
        URL bhejte hain, wo JSON mein ek "media[0].url" deta hai jahan se
        actual file download hoti hai. Video aur audio dono ke liye alag
        endpoint hai.
        """
        if self._igyt_is_blocked():
            return None

        youtube_url = self.base + video_id
        endpoint = IGYT_API["video_endpoint"] if video else IGYT_API["audio_endpoint"]
        ext = "mp4" if video else "mp3"
        filename = f"{DOWNLOAD_DIR}/{video_id}.{ext}"
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: metadata call — asli file URL isme milta hai
                async with session.get(
                    f"{IGYT_API['url']}{endpoint}",
                    params={"q": youtube_url},
                    timeout=aiohttp.ClientTimeout(total=30, connect=5),
                ) as resp:
                    if resp.status != 200:
                        body = (await resp.text())[:200]
                        logger.warning(f"[IGYT] Status: {resp.status} | Body: {body}")
                        self._igyt_mark_fail()
                        return None
                    try:
                        data = await resp.json(content_type=None)
                    except Exception as je:
                        body = (await resp.text())[:200]
                        logger.warning(
                            f"[IGYT] JSON decode failed: {type(je).__name__}: {je} | Body: {body}"
                        )
                        self._igyt_mark_fail()
                        return None

                if not data.get("success"):
                    logger.warning(f"[IGYT] success=false: {data}")
                    self._igyt_mark_fail()
                    return None

                media_list = data.get("media") or []
                file_url = data.get("primaryUrl") or (
                    media_list[0].get("url") if media_list else None
                )
                if not file_url:
                    logger.warning("[IGYT] media URL missing in response.")
                    self._igyt_mark_fail()
                    return None

                # Step 2: actual file stream/download
                async with session.get(
                    file_url,
                    timeout=aiohttp.ClientTimeout(total=90, connect=5),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"[IGYT] File status: {resp.status}")
                        self._igyt_mark_fail()
                        return None
                    with open(filename, "wb") as f:
                        async for chunk in resp.content.iter_chunked(131072):
                            f.write(chunk)

            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                self._igyt_mark_success()
                logger.info("[IGYT] Download success ✓")
                return filename

            logger.warning("[IGYT] Empty file!")
            self._igyt_mark_fail()

        except asyncio.TimeoutError:
            logger.warning("[IGYT] Error: request timed out")
            self._igyt_mark_fail()
        except Exception as e:
            # type(e).__name__ zaroori hai — kuch exceptions (jaise
            # TimeoutError) ka str() khaali hota hai, isse pehle log mein
            # sirf "[IGYT] Error: " print ho raha tha aur asli wajah pata
            # nahi chal rahi thi.
            logger.warning(f"[IGYT] Error: {type(e).__name__}: {e}")
            self._igyt_mark_fail()

        return None

    async def ytdlp_download(self, video_id: str, video: bool = False):
        url = self.base + video_id
        cookie = self.get_cookies()

        opts = {
            "outtmpl": f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
            "quiet": True,
            "nocheckcertificate": True,
        }

        if cookie:
            opts["cookiefile"] = cookie

        if video:
            opts["format"] = "bestvideo+bestaudio"
        else:
            opts["format"] = "bestaudio"

        def run():
            # FIX: 'with' block ab poora try ke andar hai. Pehle try sirf
            # extract_info() ke around tha, isliye jab context manager
            # __exit__ pe close()/save_cookies() chalta tha aur cookiefile
            # corrupt/invalid format hone ki wajah se crash hota tha, wo
            # exception yahan se bahar bubble ho jata tha aur poora
            # download() (aur uske baad ka Saavn fallback) crash kar deta
            # tha. Ab har tarah ka exception — extract_info ho ya cleanup —
            # yahin pakड़ा jayega.
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return ydl.prepare_filename(info)
            except Exception as e:
                logger.error(f"yt-dlp Error: {e}")
                return None

        return await asyncio.to_thread(run)

    async def saavn_download(self, title: str, video_id: str):
        """
        Aakhri fallback — IG-YT API aur yt-dlp dono fail ho jayein tab hi
        chalta hai. Song naam se JioSaavn pe search karta hai, video
        download nahi karta (Saavn sirf audio deta hai).
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
        file = await self.igyt_download(video_id, video)

        if file:
            return file

        logger.warning("IG-YT API failed/blocked, falling back to yt-dlp")
        file = await self.ytdlp_download(video_id, video)

        if file:
            return file

        # Sirf audio ke liye — Saavn ke paas video nahi hota
        if not video:
            logger.warning("yt-dlp bhi fail, Saavn fallback try kar rahe hain")
            return await self.saavn_download(title, video_id)

        return None
        
