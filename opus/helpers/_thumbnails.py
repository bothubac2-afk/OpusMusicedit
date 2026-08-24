# _thumbnails.py
# COMBINED LAYOUT — Full-Bleed Banner Card (from CherryMusic/anony) +
# Info Chips Row (from OpusMusic) — Apple Glassmorphism + Full Controls

import os
import aiohttp

from PIL import (
    Image,
    ImageChops,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps
)

from opus import config

# ─────────────────────────────
# THEME
# ─────────────────────────────

PURPLE = (124, 58, 237)
PURPLE_SOFT = (167, 139, 250)
WHITE = (255, 255, 255)
BG_DARK = (6, 3, 16)

SIZE = (1280, 720)

FONT_DIR = "opus/helpers/"
CACHE_DIR = "cache"


# ─────────────────────────────
# HELPERS
# ─────────────────────────────

def _linear_gradient(size, c1, c2, vertical=True):
    w, h = size
    img = Image.new("RGBA", size)
    draw = ImageDraw.Draw(img)

    if vertical:
        for y in range(h):
            t = y / h
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            draw.line((0, y, w, y), fill=(r, g, b, 255))
    else:
        for x in range(w):
            t = x / w
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            draw.line((x, 0, x, h), fill=(r, g, b, 255))

    return img


def _build_backdrop(song_img):
    """Full-bleed album art as the canvas background — minimal blur, kept sharp."""
    bg = ImageOps.fit(song_img.convert("RGB"), SIZE, method=Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(6))
    bg = ImageEnhance.Brightness(bg).enhance(0.8)
    bg = ImageEnhance.Color(bg).enhance(1.1)
    bg = bg.convert("RGBA")

    # Light overlay so foreground text/card stay readable, no heavy vignette
    overlay = Image.new("RGBA", SIZE, (*BG_DARK, 70))
    bg = Image.alpha_composite(bg, overlay)

    return bg


def _pill(base, x, y, w, h, fill, outline=None, radius=None):
    radius = radius or h // 2
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(
        (0, 0, w - 1, h - 1),
        radius=radius,
        fill=fill,
        outline=outline,
        width=1 if outline else 0
    )
    base.paste(layer, (x, y), layer)


def _gradient_text(base, draw, xy, text, font):
    tw = int(draw.textlength(text, font=font))
    th = font.size + 14

    grad = _linear_gradient((tw + 10, th), WHITE, PURPLE_SOFT, vertical=False)
    alpha = Image.new("RGBA", (tw + 10, th), (0, 0, 0, 0))
    ImageDraw.Draw(alpha).text((0, 0), text, font=font, fill=(255, 255, 255, 255))
    grad.putalpha(alpha.getchannel("A"))
    base.paste(grad, xy, grad)
    return tw


def _fit_text(draw, text, font, max_width):
    """Shrink text with ellipsis until it fits max_width."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    trimmed = text
    while draw.textlength(trimmed + "...", font=font) > max_width and len(trimmed) > 3:
        trimmed = trimmed[:-1]
    return trimmed.rstrip() + "..."


# ─────────────────────────────
# GLASS CARD (main centered panel) — true iOS-style frosted glass
# ─────────────────────────────

def _draw_glass_card(base, x, y, w, h, radius=40, blur=24, tint=(18, 16, 28, 100)):
    """
    A single uniform frosted-glass panel, matching iOS Control Center style:
    a consistently dark-tinted, semi-transparent blur so the panel reads the
    same regardless of what's behind it, plus a bright thin edge for the
    glass "rim". No separate opaque zones anywhere on the card.
    """
    crop = base.crop((x, y, x + w, y + h))
    crop = crop.filter(ImageFilter.GaussianBlur(blur))

    # consistent dark-glass tint — this is what makes it read as glass no
    # matter whether the photo behind it is bright or dark
    frost = Image.new("RGBA", (w, h), tint)
    crop = Image.alpha_composite(crop, frost)

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    crop.putalpha(mask)

    base.paste(crop, (x, y), crop)

    # faint top sheen — just enough to suggest a curved glass surface
    sheen = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sheen_grad = _linear_gradient((w, h // 3), (255, 255, 255, 20), (255, 255, 255, 0), vertical=True)
    sheen.paste(sheen_grad, (0, 0), sheen_grad)
    sheen_mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(sheen_mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    sheen.putalpha(ImageChops.multiply(sheen.getchannel("A"), sheen_mask))
    base.paste(sheen, (x, y), sheen)

    # crisp thin bright edge — the glass "rim", no drop shadow, no fill block
    border = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(border)
    d.rounded_rectangle(
        (0, 0, w - 1, h - 1), radius=radius, outline=(255, 255, 255, 100), width=2
    )
    base.paste(border, (x, y), border)


# ─────────────────────────────
# PLAYER ICONS
# ─────────────────────────────

def _draw_triangle(layer, cx, cy, size, direction="right", color=(255, 255, 255, 230)):
    d = ImageDraw.Draw(layer)
    h = size
    w = int(size * 0.85)

    if direction == "right":
        pts = [(cx - w // 2 + 2, cy - h // 2), (cx - w // 2 + 2, cy + h // 2), (cx + w // 2, cy)]
    else:
        pts = [(cx + w // 2 - 2, cy - h // 2), (cx + w // 2 - 2, cy + h // 2), (cx - w // 2, cy)]

    d.polygon(pts, fill=color)


def _draw_double_triangle(layer, cx, cy, size, direction="right", color=(255, 255, 255, 230)):
    gap = int(size * 0.28)
    if direction == "right":
        _draw_triangle(layer, cx - gap, cy, size, "right", color)
        _draw_triangle(layer, cx + gap, cy, size, "right", color)
    else:
        _draw_triangle(layer, cx + gap, cy, size, "left", color)
        _draw_triangle(layer, cx - gap, cy, size, "left", color)


def _draw_shuffle_icon(layer, cx, cy, size, color=(255, 255, 255, 180)):
    d = ImageDraw.Draw(layer)
    s = size // 2
    lw = max(2, size // 8)
    d.line([(cx - s, cy - s // 2), (cx + s, cy + s // 2)], fill=color, width=lw)
    d.line([(cx - s, cy + s // 2), (cx + s, cy - s // 2)], fill=color, width=lw)


def _draw_repeat_icon(layer, cx, cy, size, color=(255, 255, 255, 180)):
    d = ImageDraw.Draw(layer)
    r = size // 2
    lw = max(2, size // 8)
    d.arc([cx - r, cy - r, cx + r, cy + r], start=40, end=320, fill=color, width=lw)


def _draw_volume_icon(layer, cx, cy, size, color=(255, 255, 255, 180)):
    d = ImageDraw.Draw(layer)
    s = size // 2
    pts = [
        (cx - s, cy - s // 3), (cx - s // 3, cy - s // 3),
        (cx, cy - s), (cx, cy + s),
        (cx - s // 3, cy + s // 3), (cx - s, cy + s // 3)
    ]
    d.polygon(pts, fill=color)


# ─────────────────────────────
# PLAYER (full controls row, centered under title/art)
# ─────────────────────────────

def _draw_player(base, center_x, y):
    BTN = 50
    PLAY = 68
    FG = (255, 255, 255, 220)
    FG_DIM = (255, 255, 255, 150)
    ICON = 14
    GAP = 14

    def _btn(sz):
        return Image.new("RGBA", (sz, sz), (0, 0, 0, 0))

    # total row width: shuffle + prev + play + next + repeat + gaps
    row_w = BTN * 4 + PLAY + GAP * 4
    cx = center_x - row_w // 2

    # SHUFFLE
    _pill(base, cx, y, BTN, BTN, (255, 255, 255, 16), (255, 255, 255, 38), BTN // 2)
    sh = _btn(BTN)
    _draw_shuffle_icon(sh, BTN // 2, BTN // 2, ICON + 2, FG_DIM)
    base.paste(sh, (cx, y), sh)
    cx += BTN + GAP

    # PREVIOUS
    _pill(base, cx, y, BTN, BTN, (255, 255, 255, 16), (255, 255, 255, 38), BTN // 2)
    pv = _btn(BTN)
    _draw_double_triangle(pv, BTN // 2, BTN // 2, ICON, "left", FG)
    base.paste(pv, (cx, y), pv)
    cx += BTN + GAP

    # PLAY (glowing accent button)
    px, py = cx, y - (PLAY - BTN) // 2
    glow = Image.new("RGBA", (PLAY + 90, PLAY + 90), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((45, 45, PLAY + 45, PLAY + 45), fill=(*PURPLE, 130))
    glow = glow.filter(ImageFilter.GaussianBlur(32))
    base.paste(glow, (px - 45, py - 45), glow)

    _pill(base, px, py, PLAY, PLAY, (*PURPLE, 255), (*PURPLE_SOFT, 130), PLAY // 2)
    pl = _btn(PLAY)
    _draw_triangle(pl, PLAY // 2 + 5, PLAY // 2, 26, "right", WHITE)
    base.paste(pl, (px, py), pl)
    cx += PLAY + GAP

    # NEXT
    _pill(base, cx, y, BTN, BTN, (255, 255, 255, 16), (255, 255, 255, 38), BTN // 2)
    nx = _btn(BTN)
    _draw_double_triangle(nx, BTN // 2, BTN // 2, ICON, "right", FG)
    base.paste(nx, (cx, y), nx)
    cx += BTN + GAP

    # REPEAT
    _pill(base, cx, y, BTN, BTN, (255, 255, 255, 16), (255, 255, 255, 38), BTN // 2)
    rp = _btn(BTN)
    _draw_repeat_icon(rp, BTN // 2, BTN // 2, ICON + 2, FG_DIM)
    base.paste(rp, (cx, y), rp)


# ─────────────────────────────
# INFO CHIPS ROW (views / duration / quality) — ported from OpusMusic
# ─────────────────────────────

def _draw_chips(base, draw, center_x, y, chips, font):
    """Row of small pill chips, centered as a group under the title."""
    widths = [int(draw.textlength(c, font=font)) + 40 for c in chips]
    gap = 16
    total_w = sum(widths) + gap * (len(chips) - 1)
    cx = center_x - total_w // 2

    for c, cw in zip(chips, widths):
        _pill(base, cx, y, cw, 40, (255, 255, 255, 16), (255, 255, 255, 35), 20)
        tw = int(draw.textlength(c, font=font))
        draw.text((cx + (cw - tw) // 2, y + 10), c, font=font, fill=(255, 255, 255, 190))
        cx += cw + gap


# ─────────────────────────────
# PROGRESS (with real elapsed-based fill)
# ─────────────────────────────

def _time_to_seconds(t):
    try:
        parts = [int(p) for p in str(t).split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        h, m, s = parts[-3:]
        return h * 3600 + m * 60 + s
    except Exception:
        return 0


def _draw_progress(base, draw, x, y, width, cur, end, font):
    draw.text((x, y - 26), cur, font=font, fill=(255, 255, 255, 170))
    rw = int(draw.textlength(end, font=font))
    draw.text((x + width - rw, y - 26), end, font=font, fill=(255, 255, 255, 170))

    track = Image.new("RGBA", (width, 6), (0, 0, 0, 0))
    ImageDraw.Draw(track).rounded_rectangle((0, 0, width - 1, 5), radius=3, fill=(255, 255, 255, 35))
    base.paste(track, (x, y), track)

    cur_s = _time_to_seconds(cur)
    end_s = max(_time_to_seconds(end), 1)
    ratio = min(max(cur_s / end_s, 0.02), 1.0)
    fw = max(6, int(width * ratio))

    fill = _linear_gradient((fw, 6), PURPLE, PURPLE_SOFT, vertical=False)
    mask = Image.new("L", (fw, 6), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, fw - 1, 5), radius=3, fill=255)
    fill.putalpha(mask)
    base.paste(fill, (x, y), fill)

    # knob
    knob_d = 14
    kx = x + fw - knob_d // 2
    ky = y - 4
    knob = Image.new("RGBA", (knob_d, knob_d), (0, 0, 0, 0))
    kd = ImageDraw.Draw(knob)
    kd.ellipse((0, 0, knob_d - 1, knob_d - 1), fill=WHITE)
    base.paste(knob, (kx, ky), knob)


# ─────────────────────────────
# MAIN CLASS
# ─────────────────────────────

class Thumbnail:

    def __init__(self):
        self.session = None

        os.makedirs(CACHE_DIR, exist_ok=True)

        self.f_title = ImageFont.truetype(FONT_DIR + "Raleway-Bold.ttf", 46)
        self.f_small = ImageFont.truetype(FONT_DIR + "Inter-Light.ttf", 24)
        self.f_badge = ImageFont.truetype(FONT_DIR + "Inter-Light.ttf", 18)
        self.f_brand = ImageFont.truetype(FONT_DIR + "Raleway-Bold.ttf", 26)
        self.f_power = ImageFont.truetype(FONT_DIR + "Inter-Light.ttf", 16)

    async def start(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    async def save_thumb(self, path, url):
        if not self.session:
            self.session = aiohttp.ClientSession()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        async with self.session.get(url) as resp:
            with open(path, "wb") as f:
                f.write(await resp.read())
        return path

    async def generate(self, song):
        try:
            W, H = SIZE
            temp = f"{CACHE_DIR}/temp_{song.id}.jpg"
            output = f"{CACHE_DIR}/{song.id}.png"

            await self.save_thumb(temp, song.thumbnail)
            raw = Image.open(temp).convert("RGBA")

            # 1) Full-bleed blurred backdrop across the ENTIRE canvas
            base = _build_backdrop(raw)
            draw = ImageDraw.Draw(base)

            # 2) Centered glass card (wide enough for the banner art, tall enough for all content)
            CARD_W, CARD_H = 800, 660
            CARD_X = (W - CARD_W) // 2
            CARD_Y = (H - CARD_H) // 2

            _draw_glass_card(base, CARD_X, CARD_Y, CARD_W, CARD_H, radius=44)

            inner_x = CARD_X + 60
            content_w = CARD_W - 120

            # 3) Full-bleed banner art — stretches edge-to-edge across the TOP
            # of the card, flush with the card's own rounded corners, so there
            # is no gap/border where the card's glass tint could show through
            ART_W, ART_H = CARD_W, 280
            art = ImageOps.fit(raw, (ART_W, ART_H), method=Image.LANCZOS)

            # mask: rounded only on the top two corners (matches card top),
            # square on the bottom edge where it meets the rest of the card
            art_mask = Image.new("L", (ART_W, ART_H), 0)
            amd = ImageDraw.Draw(art_mask)
            amd.rounded_rectangle((0, 0, ART_W - 1, ART_H - 1 + 44), radius=44, fill=255)
            amd.rectangle((0, ART_H - 44, ART_W - 1, ART_H - 1), fill=255)
            art.putalpha(art_mask)

            art_x = CARD_X
            art_y = CARD_Y

            base.paste(art, (art_x, art_y), art)

            # thin bright edge along the bottom of the art, separating it
            # from the glass body below (no border around the whole art —
            # it's flush with the card, not a floating tile)
            seam = Image.new("RGBA", (ART_W, 2), (255, 255, 255, 70))
            base.paste(seam, (art_x, art_y + ART_H - 2), seam)

            cursor_y = art_y + ART_H + 24

            # 4) "NOW PLAYING" — small overlay chip in the top-left corner of
            # the art itself, out of the way, instead of its own centered row
            badge = "▶ NOW PLAYING"
            bw = int(draw.textlength(badge, font=self.f_badge)) + 30
            bx = art_x + 20
            by = art_y + 18
            _pill(base, bx, by, bw, 32, (10, 8, 16, 150), (255, 255, 255, 90), 16)
            draw.text((bx + 15, by + 6), badge, font=self.f_badge, fill=(255, 255, 255, 235))

            # 5) Title, centered, gradient, fit to card width
            title = _fit_text(draw, song.title.strip(), self.f_title, content_w)
            tw = int(draw.textlength(title, font=self.f_title))
            _gradient_text(base, draw, (CARD_X + (CARD_W - tw) // 2, cursor_y), title, self.f_title)
            cursor_y += self.f_title.size + 10

            # 6) Channel name, centered, dim
            channel = _fit_text(draw, song.channel_name, self.f_small, content_w)
            cw = int(draw.textlength(channel, font=self.f_small))
            draw.text((CARD_X + (CARD_W - cw) // 2, cursor_y), channel, font=self.f_small, fill=(255, 255, 255, 175))
            cursor_y += self.f_small.size + 18

            # 7) Info chips row (views / duration / quality) — ported from OpusMusic layout
            chips = [c for c in [song.view_count, song.duration, "HD Audio"] if c]
            if chips:
                _draw_chips(base, draw, CARD_X + CARD_W // 2, cursor_y, chips, self.f_badge)
                cursor_y += 40 + 24

            # 8) Progress bar, centered, full card width minus padding
            progress_w = content_w
            _draw_progress(base, draw, inner_x, cursor_y, progress_w, "0:01", song.duration, self.f_badge)
            cursor_y += 50

            # 9) Full player controls, centered — PLAY button is taller than
            # the row baseline, so leave room below it before the watermark
            _draw_player(base, CARD_X + CARD_W // 2, cursor_y)
            cursor_y += 68 + 26

            # 10) Watermark, INSIDE the card, below the player — never clipped
            wm1 = "TulipMusic"
            wm2 = "Powered by AlfaBots"
            w1 = int(draw.textlength(wm1, font=self.f_brand))
            w2 = int(draw.textlength(wm2, font=self.f_power))

            _gradient_text(base, draw, (CARD_X + (CARD_W - w1) // 2, cursor_y), wm1, self.f_brand)
            draw.text(
                (CARD_X + (CARD_W - w2) // 2, cursor_y + self.f_brand.size + 6),
                wm2, font=self.f_power, fill=(255, 255, 255, 165)
            )

            base.save(output)

            try:
                os.remove(temp)
            except OSError:
                pass

            return output

        except Exception as e:
            print(f"[Thumbnail] generation failed: {e}")
            return config.DEFAULT_THUMB
