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

# ── Multi-API Config ──────────────────────────────────────────
APIS = [
    {
        "url": "https://api.shrutibots.site",
        "key": "ShrutiBotssWg4dn7KsrjaVwgjpq4j",
        "param": "api_key",
        "endpoint": "/download",
    },
    {
        "url": "https://api01.shrutibots.site",
        "key": "ShrutiBotsv5GJeaWIfzejJ8o0xnhw",
        "param": "api_key",
        "endpoint": "/download",
    },
    {
        "url": "https://api01.shrutibots.site",
        "key": "ShrutiBotsvoySy5NkjijEJCL9arWK",
        "param": "api_key",
        "endpoint": "/download",
    },
]

# Saavn — sabse aakhri fallback. Song *naam* se search karta hai (video ID se
# nahi), isliye sirf tab kaam karta hai jab humare paas title ho (search se
# aaye Track, ya URL-based request mein yt-dlp se mila title). YouTube ke
# rate-limit/block wali windows mein temporary safety net ki tarah use hota
# hai — proxy/cookie/Deno kuch nahi chahiye.
SAAVN_API = "https://saavn-api-eight.vercel.app"

FAIL_THRESHOLD = 3
BLOCK_DURATION = 5 * 3600  # 5 hours
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
        self._api_index = 0

        # Circuit Breaker — har API ka unique identifier key se banao
        self._fail_count = {self._api_id(api): 0 for api in APIS}
        self._blocked_until = {self._api_id(api): 0 for api in APIS}

    def _api_id(self, api: dict) -> str:
        """Same URL par bhi alag key ho to unique ID banao"""
        return f"{api['url']}::{api['key']}"

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

    # ── Circuit Breaker ───────────────────────────────────────

    def _is_blocked(self, api: dict) -> bool:
        aid = self._api_id(api)
        now = time.time()

        if now < self._blocked_until[aid]:
            remaining = int((self._blocked_until[aid] - now) / 3600)
            logger.info(f"[{aid}] Blocked! ~{remaining}h remaining.")
            return True

        if self._fail_count[aid] >= FAIL_THRESHOLD:
            logger.info(f"[{aid}] Block khatam, phir se try karega.")
            self._fail_count[aid] = 0

        return False

    def _mark_fail(self, api: dict):
        aid = self._api_id(api)
        self._fail_count[aid] += 1
        logger.warning(
            f"[{api['url']}] Fail count: {self._fail_count[aid]}/{FAIL_THRESHOLD}"
        )

        if self._fail_count[aid] >= FAIL_THRESHOLD:
            self._blocked_until[aid] = time.time() + BLOCK_DURATION
            logger.warning(f"[{api['url']}] Blocked for 5 hours!")

    def _mark_success(self, api: dict):
        aid = self._api_id(api)
        self._fail_count[aid] = 0
        self._blocked_until[aid] = 0
        logger.info(f"[{api['url']}] Success! Fail count reset.")

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

    async def _try_single_api(self, api: dict, video_id: str, video: bool):
        try:
            youtube_url = self.base + video_id
            ext = "mp4" if video else "mp3"
            filename = f"{DOWNLOAD_DIR}/{video_id}.{ext}"
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)

            params = {
                "url": youtube_url,
                "type": "video" if video else "audio",
            }
            if api["key"] and api["param"]:
                params[api["param"]] = api["key"]

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api['url']}{api['endpoint']}",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=60, connect=5),
                ) as resp:

                    if resp.status != 200:
                        logger.warning(
                            f"[{api['url']}] Status: {resp.status}"
                        )
                        self._mark_fail(api)
                        return None

                    with open(filename, "wb") as f:
                        async for chunk in resp.content.iter_chunked(131072):
                            f.write(chunk)

            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                self._mark_success(api)
                logger.info(f"[{api['url']}] Download success ✓")
                return filename
            else:
                logger.warning(f"[{api['url']}] Empty file!")
                self._mark_fail(api)

        except Exception as e:
            logger.warning(f"[{api['url']}] Error: {e}")
            self._mark_fail(api)

        return None

    async def api_download(self, video_id: str, video: bool = False):
        available = [api for api in APIS if not self._is_blocked(api)]

        if not available:
            logger.error("Saari APIs blocked! yt-dlp fallback.")
            return None

        start = self._api_index % len(available)
        ordered = available[start:] + available[:start]
        self._api_index += 1

        for api in ordered:
            logger.info(
                f"Trying: {api['url']} key: {api['key'][:8]}... "
                f"(fails: {self._fail_count[self._api_id(api)]}/{FAIL_THRESHOLD})"
            )
            result = await self._try_single_api(api, video_id, video)
            if result:
                return result

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
        Aakhri fallback — YouTube ke saare tareeke (APIs + yt-dlp) fail ho
        jayein tab hi chalta hai. Song naam se JioSaavn pe search karta hai,
        video download nahi karta (Saavn sirf audio deta hai).
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
        file = await self.api_download(video_id, video)

        if file:
            return file

        logger.warning("All APIs failed/blocked, falling back to yt-dlp")
        file = await self.ytdlp_download(video_id, video)

        if file:
            return file

        # Sirf audio ke liye — Saavn ke paas video nahi hota
        if not video:
            logger.warning("yt-dlp bhi fail, Saavn fallback try kar rahe hain")
            return await self.saavn_download(title, video_id)

        return None
    
