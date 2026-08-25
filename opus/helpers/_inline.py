# Copyright (c) 2025 OpusMusic
# Licensed under the MIT License.
# This file is part of OpusMusic

from pyrogram import types, enums

from opus import app, config, lang
from opus.core.lang import lang_codes


class Inline:
    def __init__(self):
        self.ikm = types.InlineKeyboardMarkup
        self.ikb = types.InlineKeyboardButton

    def cancel_dl(self, text) -> types.InlineKeyboardMarkup:
        return self.ikm([[self.ikb(text=text, callback_data=f"cancel_dl",
                                   style=enums.ButtonStyle.DANGER)]])

    def controls(
        self,
        chat_id: int,
        status: str = None,
        timer: str = None,
        remove: bool = False,
        autoplay_on: bool = False,
        autoplay_text: str = "ᴀᴜᴛᴏᴘʟᴀʏ: ᴏꜰꜰ ❌",
    ) -> types.InlineKeyboardMarkup:
        keyboard = []
        if status:
            keyboard.append(
                [self.ikb(text=status, callback_data=f"controls status {chat_id}",
                          style=enums.ButtonStyle.PRIMARY)]
            )
        elif timer:
            keyboard.append(
                [self.ikb(text=timer, callback_data=f"controls status {chat_id}",
                          style=enums.ButtonStyle.PRIMARY)]
            )

        if not remove:
            keyboard.append(
                [
                    self.ikb(text="▷", callback_data=f"controls resume {chat_id}",
                             style=enums.ButtonStyle.SUCCESS),
                    self.ikb(text="II", callback_data=f"controls pause {chat_id}",
                             style=enums.ButtonStyle.PRIMARY),
                    self.ikb(text="⥁", callback_data=f"controls replay {chat_id}",
                             style=enums.ButtonStyle.PRIMARY),
                    self.ikb(text="‣‣I", callback_data=f"controls skip {chat_id}",
                             style=enums.ButtonStyle.PRIMARY),
                    self.ikb(text="▢", callback_data=f"controls stop {chat_id}",
                             style=enums.ButtonStyle.DANGER),
                ]
            )
            keyboard.append(
                [
                    self.ikb(
                        text=autoplay_text,
                        callback_data=f"controls autoplay {chat_id}",
                        style=enums.ButtonStyle.SUCCESS if autoplay_on else enums.ButtonStyle.DANGER,
                    )
                ]
            )
        return self.ikm(keyboard)

    def help_markup(
        self, _lang: dict, back: bool = False
    ) -> types.InlineKeyboardMarkup:
        if back:
            rows = [
                [
                    self.ikb(text=_lang["back"], callback_data="help back",
                             style=enums.ButtonStyle.PRIMARY),
                    self.ikb(text=_lang["close"], callback_data="help close",
                             style=enums.ButtonStyle.DANGER),
                ]
            ]
        else:
            cbs = ["admins", "auth", "blist", "lang", "ping", "play", "queue", "stats", "sudo"]
            buttons = [
                self.ikb(text=_lang[f"help_{i}"], callback_data=f"help {cb}",
                         style=enums.ButtonStyle.PRIMARY)
                for i, cb in enumerate(cbs)
            ]
            rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]

        return self.ikm(rows)

    def lang_markup(self, _lang: str) -> types.InlineKeyboardMarkup:
        langs = lang.get_languages()

        buttons = [
            self.ikb(
                text=f"{name} ({code}) {'✔️' if code == _lang else ''}",
                callback_data=f"lang_change {code}",
                style=enums.ButtonStyle.SUCCESS if code == _lang else enums.ButtonStyle.PRIMARY,
            )
            for code, name in langs.items()
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        return self.ikm(rows)

    def ping_markup(self, text: str) -> types.InlineKeyboardMarkup:
        return self.ikm([[self.ikb(text=text, url=config.SUPPORT_CHAT,
                                   style=enums.ButtonStyle.PRIMARY)]])

    def play_queued(
        self, chat_id: int, item_id: str, _text: str
    ) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(
                        text=_text, callback_data=f"controls force {chat_id} {item_id}",
                        style=enums.ButtonStyle.SUCCESS,
                    )
                ]
            ]
        )

    def queue_markup(
        self, chat_id: int, _text: str, playing: bool
    ) -> types.InlineKeyboardMarkup:
        _action = "pause" if playing else "resume"
        _style = enums.ButtonStyle.PRIMARY if playing else enums.ButtonStyle.SUCCESS
        return self.ikm(
            [[self.ikb(text=_text, callback_data=f"controls {_action} {chat_id} q",
                       style=_style)]]
        )

    def settings_markup(
        self, lang: dict, admin_only: bool, cmd_delete: bool, language: str, chat_id: int
    ) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(
                        text=lang["play_mode"] + " ➜",
                        callback_data="settings",
                        style=enums.ButtonStyle.PRIMARY,
                    ),
                    self.ikb(text=admin_only, callback_data="settings play",
                             style=enums.ButtonStyle.SUCCESS),
                ],
                [
                    self.ikb(
                        text=lang["cmd_delete"] + " ➜",
                        callback_data="settings",
                        style=enums.ButtonStyle.PRIMARY,
                    ),
                    self.ikb(text=cmd_delete, callback_data="settings delete",
                             style=enums.ButtonStyle.SUCCESS),
                ],
                [
                    self.ikb(
                        text=lang["language"] + " ➜",
                        callback_data="settings",
                        style=enums.ButtonStyle.PRIMARY,
                    ),
                    self.ikb(text=lang_codes[language], callback_data="language",
                             style=enums.ButtonStyle.SUCCESS),
                ],
            ]
        )

    # ============================================
    # MODIFIED: Source button opens submenu
    # ============================================
    def start_key(
        self, lang: dict, private: bool = False
    ) -> types.InlineKeyboardMarkup:
        rows = [
            [
                self.ikb(
                    text=lang["add_me"],
                    url=f"https://t.me/{app.username}?startgroup=true",
                    style=enums.ButtonStyle.SUCCESS,
                )
            ],
            [self.ikb(text=lang["help"], callback_data="help",
                      style=enums.ButtonStyle.PRIMARY)],
            [
                self.ikb(text=lang["support"], url=config.SUPPORT_CHAT,
                         style=enums.ButtonStyle.SUCCESS),
                self.ikb(text=lang["channel"], url=config.SUPPORT_CHANNEL,
                         style=enums.ButtonStyle.DANGER),
            ],
        ]
        if private:
            # Source button opens submenu via callback
            rows += [
                [
                    self.ikb(
                        text=lang["source"],
                        callback_data="source_menu",
                        style=enums.ButtonStyle.PRIMARY,
                    )
                ]
            ]
        else:
            rows += [[self.ikb(text=lang["language"], callback_data="language",
                               style=enums.ButtonStyle.PRIMARY)]]
        return self.ikm(rows)

    # ============================================
    # SOURCE SUBMENU: Username-based ONLY
    # NO User ID system - direct profile links
    # ============================================
    def source_markup(self, lang: dict) -> types.InlineKeyboardMarkup:
        """
        Source submenu - Click pe direct Telegram profile khulega

        Row 1: Owner
        Row 2: Source Code | Any Quastion
        Row 3: Developer
        Row 4: Back | Close

        NOTE: Sirf username dalna hai, User ID ki zaroorat nahi!
        """
        return self.ikm(
            [
                [
                    self.ikb(text="👑 𝐎𝗐𝗇𝖾𝗋", url="https://t.me/realitywasalie",
                             style=enums.ButtonStyle.PRIMARY),
                ],
                [
                    self.ikb(text="🔧 𝐒𝗈𝗎𝗋𝖼𝖾 𝐂𝗈𝖽𝖾", url="https://github.com/TeamAlfaBots/OpusMusic-",
                             style=enums.ButtonStyle.DANGER),
                    self.ikb(text="💬 𝐀𝗇𝗒 𝐐𝗎𝖺𝗌𝗍𝗂𝗈𝗇", url="https://t.me/II_DEAD_SOUL",
                             style=enums.ButtonStyle.DANGER),
                ],
                [
                    self.ikb(text="💻 𝐃𝖾𝗏𝖾𝗅𝗈𝗉𝖾𝗋", url="https://t.me/Ucan_callme_X",
                             style=enums.ButtonStyle.SUCCESS),
                ],
                [
                    self.ikb(text=lang.get("back", "⇲ 𝐁𝖺𝖼𝗄"), callback_data="source_back",
                             style=enums.ButtonStyle.PRIMARY),
                    self.ikb(text=lang.get("close", "❌ 𝐂𝗅𝗈𝗌𝖾"), callback_data="help close",
                             style=enums.ButtonStyle.DANGER),
                ],
            ]
        )

    def yt_key(self, link: str) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(text="❐", copy_text=link,
                             style=enums.ButtonStyle.PRIMARY),
                    self.ikb(text="Youtube", url=link,
                             style=enums.ButtonStyle.DANGER),
                ],
            ]
      )
      
