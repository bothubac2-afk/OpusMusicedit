# Copyright (c) 2025 OpusMusic
# Licensed under the MIT License.
# This file is part of OpusMusic

import asyncio
import random
from datetime import datetime

from pyrogram import enums, filters, types

from opus import app, config, db, lang
from opus.helpers import buttons, utils

# ── Optional config ───────────────────────────────────────────────────────────
STICKER_ID: str | None = getattr(config, "STICKER_ID", None)

_REACTIONS = ["🎵", "✨", "💎", "🎶", "👑", "🌟", "🎼", "💫", "🎧"]

_LOADING_FRAMES = [
    "░░░░░░░░░░  <b>ᴄσηηєᴄᴛɪηɢ...</b>",
    "███░░░░░░░  <b>ʟσᴧᴅɪηɢ ϻσᴅᴜʟєꜱ...</b>",
    "██████░░░░  <b>ꜱʏηᴄɪηɢ ᴅᴧᴛᴧʙᴧꜱєꜱ...</b>",
    "█████████░  <b>ᴧʟϻσꜱᴛ ʀєᴧᴅʏ...</b>",
    "██████████  <b>✦ ᴡєʟᴄσϻє ᴛσ σᴘᴜꜱϻᴜꜱɪᴄ ✦</b>",
]

_TIPS = [
    "✦ ꜱᴛʀєᴧϻ ϻᴜꜱɪᴄ ᴡɪᴛʜ <code>/play &lt;song&gt;</code>",
    "✦ ᴘʟᴧʏ ᴠɪᴅєσꜱ ᴡɪᴛʜ <code>/vplay &lt;song&gt;</code>",
    "✦ ᴠɪєᴡ ᴄᴜʀʀєηᴛ qᴜєᴜє ᴡɪᴛʜ <code>/queue</code>",
    "✦ ꜱᴋɪᴘ ᴛʀᴧᴄᴋꜱ ɪηꜱᴛᴧηᴛʟʏ ᴡɪᴛʜ <code>/skip</code>",
    "✦ ꜰɪηє-ᴛᴜηє ʏσᴜʀ єxᴘєʀɪєηᴄє ᴠɪᴧ <code>/settings</code>",
]

_DIVIDER = "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_start_img() -> str:
    if isinstance(config.START_IMG, list) and config.START_IMG:
        return random.choice(config.START_IMG)
    return config.START_IMG


def _time_greeting() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "🌅 ɢσσᴅ ϻσʀηɪηɢ"
    if 12 <= hour < 17:
        return "🌞 ɢσσᴅ ᴧꜰᴛєʀησση"
    if 17 <= hour < 21:
        return "🌆 ɢσσᴅ єᴠєηɪηɢ"
    return "🌙 ɢσσᴅ ηɪɢʜᴛ"


def _premium_caption(base_text: str, first_name: str) -> str:
    greeting = _time_greeting()
    tip = random.choice(_TIPS)
    version = getattr(config, "VERSION", "2.0")
    return (
        f"✦ {greeting}, <b>{first_name}</b> 👋\n\n"
        f"{base_text}\n\n"
        f"{_DIVIDER}\n"
        f"<b>◈ {app.name}</b>  <code>v{version}</code>\n"
        f"{tip}\n"
        f"{_DIVIDER}"
    )


def _group_caption(base_text: str) -> str:
    version = getattr(config, "VERSION", "2.0")
    return (
        f"{base_text}\n\n"
        f"{_DIVIDER}\n"
        f"<b>◈ {app.name}</b>  <code>v{version}</code>\n"
        f"✦ High-quality • Low-latency • Always on\n"
        f"{_DIVIDER}"
    )


async def _react(message: types.Message, emoji: str) -> None:
    try:
        await message.react(emoji)
    except Exception:
        pass


async def _send_sticker(message: types.Message) -> None:
    if not STICKER_ID:
        return
    try:
        sticker_msg = await message.reply_sticker(STICKER_ID)
        await asyncio.sleep(2)
        await sticker_msg.delete()
    except Exception:
        pass


async def _loading_animation(message: types.Message) -> None:
    try:
        loading = await message.reply_text(
            _LOADING_FRAMES[0],
            parse_mode=enums.ParseMode.HTML,
        )
        for frame in _LOADING_FRAMES[1:]:
            await asyncio.sleep(0.35)
            await loading.edit_text(frame, parse_mode=enums.ParseMode.HTML)
        await asyncio.sleep(0.4)
        await loading.delete()
    except Exception:
        pass


# ── Handlers ──────────────────────────────────────────────────────────────────

@app.on_message(filters.command(["help"]) & filters.private & ~app.bl_users)
@lang.language()
async def _help(_, m: types.Message):
    await m.reply_text(
        text=m.lang["help_menu"],
        reply_markup=buttons.help_markup(m.lang),
        quote=True,
    )


@app.on_message(filters.command(["start"]))
@lang.language()
async def start(_, message: types.Message):
    # Blocked user guard
    if message.from_user.id in app.bl_users and message.from_user.id not in db.notified:
        return await message.reply_text(message.lang["bl_user_notify"])

    # /start help deep-link
    if len(message.command) > 1 and message.command[1] == "help":
        return await _help(_, message)

    private = message.chat.type == enums.ChatType.PRIVATE

    # 1. Typing action
    try:
        await app.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
        await asyncio.sleep(0.3)
    except Exception:
        pass

    # 2. React to /start message
    asyncio.create_task(_react(message, random.choice(_REACTIONS)))

    # 3. Loading animation (private only)
    if private:
        await _loading_animation(message)

    # 4. Sticker animation (private only)
    if private:
        asyncio.create_task(_send_sticker(message))

    # 5. Build caption
    base_text = (
        message.lang["start_pm"].format(message.from_user.first_name, app.name)
        if private
        else message.lang["start_gp"].format(app.name)
    )

    _text = (
        _premium_caption(base_text, message.from_user.first_name)
        if private
        else _group_caption(base_text)
    )

    # 6. Buttons
    key = buttons.start_key(message.lang, private)

    if private:
        # ── PRIVATE: Text first → then Photo + Buttons ────────────────────
        try:
            await message.reply_text(
                text=_text,
                quote=True,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass

        # Small delay so text appears before image
        await asyncio.sleep(0.3)

        # Photo + Buttons (no caption)
        sent = None
        try:
            sent = await app.send_photo(
                chat_id=message.chat.id,
                photo=get_start_img(),
                reply_markup=key,
            )
        except Exception:
            # Fallback: just send buttons as text if photo fails
            sent = await message.reply_text(
                text="🎵",
                reply_markup=key,
                quote=False,
            )

    else:
        # ── GROUP: Photo + Caption + Buttons (single message) ─────────────
        sent = None
        try:
            sent = await message.reply_photo(
                photo=get_start_img(),
                caption=_text,
                reply_markup=key,
                quote=False,
            )
        except Exception:
            sent = await message.reply_text(
                text=_text,
                reply_markup=key,
                quote=False,
                parse_mode=enums.ParseMode.HTML,
            )

    # 7. React to last sent message
    if sent:
        asyncio.create_task(_react(sent, "💎"))

    # 8. Save user / chat
    if private:
        if await db.is_user(message.from_user.id):
            return
        await utils.send_log(message)
        await db.add_user(message.from_user.id)
    else:
        if await db.is_chat(message.chat.id):
            return
        await utils.send_log(message, True)
        await db.add_chat(message.chat.id)


@app.on_message(filters.command(["playmode", "settings"]) & filters.group & ~app.bl_users)
@lang.language()
async def settings(_, message: types.Message):
    admin_only = await db.get_play_mode(message.chat.id)
    cmd_delete = await db.get_cmd_delete(message.chat.id)
    _language = await db.get_lang(message.chat.id)
    await message.reply_text(
        text=message.lang["start_settings"].format(message.chat.title),
        reply_markup=buttons.settings_markup(
            message.lang, admin_only, cmd_delete, _language, message.chat.id
        ),
        quote=True,
    )


@app.on_message(filters.new_chat_members, group=7)
@lang.language()
async def _new_member(_, message: types.Message):
    if message.chat.type != enums.ChatType.SUPERGROUP:
        return await message.chat.leave()

    await asyncio.sleep(3)
    for member in message.new_chat_members:
        if member.id == app.id:
            if await db.is_chat(message.chat.id):
                return
            await utils.send_log(message, True)
            await db.add_chat(message.chat.id)
          
