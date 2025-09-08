import os
import io
import json
from typing import Dict, Any, List, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageFilter
from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# =============================
# Config & Globals
# =============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Load color & font registries
COLORS: Dict[str, Dict[str, str]] = {}
FONTS: Dict[str, Dict[str, str]] = {}

if os.path.exists("colors.json"):
    with open("colors.json", "r", encoding="utf-8") as f:
        COLORS = json.load(f)
else:
    COLORS = {
        "basic": {
            "black": "#000000",
            "white": "#FFFFFF",
            "gray": "#808080",
            "red": "#FF0000",
            "blue": "#0000FF",
            "green": "#00FF00",
            "yellow": "#FFFF00",
            "orange": "#FFA500",
            "purple": "#800080",
            "pink": "#FFC0CB",
        },
        "extended": {
            "cyan": "#00FFFF",
            "magenta": "#FF00FF",
            "lime": "#32CD32",
            "teal": "#008080",
            "indigo": "#4B0082",
            "brown": "#A52A2A",
            "gold": "#FFD700",
            "silver": "#C0C0C0",
            "navy": "#000080",
            "maroon": "#800000",
        },
    }

if os.path.exists("fonts.json"):
    with open("fonts.json", "r", encoding="utf-8") as f:
        FONTS = json.load(f)
else:
    # Minimal fallback
    FONTS = {
        "Roboto": {
            "Regular": "Roboto-Regular.ttf",
            "Bold": "Roboto-Bold.ttf",
            "Italic": "Roboto-Italic.ttf"
        }
    }

# Canvas defaults
CANVAS_SIZE = (1080, 1920)  # portrait

# =============================
# Conversation States
# =============================
(
    MANGA_IMG,
    MANGA_NAME,
    SYNOPSIS,
    AUTHOR,
    YEAR,
    CHAPTERS,
    PERCENTAGE,
    PERCENTAGE_BOX_POSITION,
    PERCENTAGE_BOX_BG,
    PERCENTAGE_BOX_ALPHA,
    PERCENTAGE_BOX_BORDER,
    PERCENTAGE_BOX_RADIUS,
    PERCENTAGE_BOX_CHAPTERS,
    BADGE_START,
    BADGE_TEXT,
    BADGE_BG,
    BADGE_TEXT_COLOR,
    BADGE_ALPHA,
    BADGE_RADIUS,
    BADGE_POSITION,
    TEMPLATE,
    BACKGROUND_TYPE,
    BACKGROUND_DETAIL,
    LAYOUT,
    EFFECTS,
    EXPORT_FORMAT,
    BRANDING,
    FONT_FAMILY_STYLE,
    TITLE_SIZE,
    AUTHOR_SIZE,
    SYNOPSIS_SIZE,
    BRANDING_SIZE,
    TITLE_COLOR,
    AUTHOR_COLOR,
    SYNOPSIS_COLOR,
    BRANDING_COLOR,
) = range(36)

# In-memory per-chat data (simple demo)
SESSIONS: Dict[int, Dict[str, Any]] = {}

# =============================
# Helpers
# =============================

def session(update: Update) -> Dict[str, Any]:
    cid = update.effective_chat.id
    if cid not in SESSIONS:
        SESSIONS[cid] = {
            "badges": [],
            "template": "classic",
            "background_type": "solid",
            "background_color": "#FFFFFF",
            "layout": "left",
            "effects": [],
            "export": "jpg",
            "font": ("Roboto", "Regular"),
            "title_size": 50,
            "author_size": 35,
            "synopsis_size": 30,
            "branding_size": 25,
            "title_color": "#000000",
            "author_color": "#000000",
            "synopsis_color": "#000000",
            "branding_color": "#808080",
            "branding": "waalords",
            "percentage": 0,
            "chapters": "0",
            "percentage_box_position": "bottom-right",
            "percentage_box_bg": "#FFFFFF",
            "percentage_box_alpha": 220,
            "percentage_box_border": "#000000",
            "percentage_box_radius": 30,
            "percentage_box_chapters": True,
        }
    return SESSIONS[cid]


def parse_color(val: str, default: str = "#000000") -> Tuple[int, int, int]:
    if not val:
        val = default
    val = val.strip()
    # Try named color from COLORS
    for group in COLORS.values():
        if val.lower() in group:
            val = group[val.lower()]
            break
    try:
        return ImageColor.getrgb(val)
    except Exception:
        try:
            return ImageColor.getrgb(default)
        except Exception:
            return (0, 0, 0)


def get_font(family: str, style: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        filename = FONTS[family][style]
        path = os.path.join("assets", "fonts", filename)
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def word_wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    line = ""
    for w in words:
        test = (line + " " + w).strip()
        wlen, _ = draw.textsize(test, font=font)
        if wlen <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def rounded_image(im: Image.Image, radius: int) -> Image.Image:
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    mask = Image.new("L", im.size, 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([0, 0, im.size[0], im.size[1]], radius=radius, fill=255)
    im.putalpha(mask)
    return im

# =============================
# Drawing building blocks
# =============================

def draw_background(base: Image.Image, data: Dict[str, Any]) -> Image.Image:
    w, h = base.size
    btype = data.get("background_type", "solid")
    if btype == "solid":
        color = parse_color(data.get("background_color", "#FFFFFF"))
        bg = Image.new("RGB", (w, h), color)
        return bg.convert("RGBA")
    elif btype == "gradient":
        colors = data.get("background_colors", ["#000000", "#FFFFFF"])  # [c1, c2]
        try:
            c1 = parse_color(colors[0])
            c2 = parse_color(colors[1])
        except Exception:
            c1 = (0, 0, 0)
            c2 = (255, 255, 255)
        grad = Image.new("RGB", (w, h))
        gdraw = ImageDraw.Draw(grad)
        for y in range(h):
            r = int(c1[0] * (1 - y / h) + c2[0] * (y / h))
            g = int(c1[1] * (1 - y / h) + c2[1] * (y / h))
            b = int(c1[2] * (1 - y / h) + c2[2] * (y / h))
            gdraw.line([(0, y), (w, y)], fill=(r, g, b))
        return grad.convert("RGBA")
    elif btype == "pattern":
        style = data.get("pattern_style", "stripes")
        color_bg = parse_color(data.get("pattern_bg", "#111111"))
        color_fg = parse_color(data.get("pattern_fg", "#222222"))
        bg = Image.new("RGB", (w, h), color_bg)
        gdraw = ImageDraw.Draw(bg)
        if style == "dots":
            step = 48
            for y in range(0, h, step):
                for x in range(0, w, step):
                    gdraw.ellipse([x, y, x + 12, y + 12], fill=color_fg)
        elif style == "noise":
            import random
            px = bg.load()
            for y in range(h):
                for x in range(w):
                    if (x + y) % 7 == 0:
                        px[x, y] = color_fg
        else:  # stripes
            for y in range(0, h, 24):
                gdraw.rectangle([0, y, w, y + 12], fill=color_fg)
        return bg.convert("RGBA")
    elif btype == "image" and data.get("background_image"):
        try:
            bg = Image.open(io.BytesIO(data["background_image"]))
            bg = bg.convert("RGBA").resize((w, h))
            return bg
        except Exception:
            pass
    # default to transparent
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def draw_thumbnail(canvas: Image.Image, thumb: Image.Image, data: Dict[str, Any]) -> Image.Image:
    w, h = canvas.size
    layout = data.get("layout", "left")  # left/right/top/overlay
    effects = data.get("effects", [])

    # Base thumb size
    if layout == "top":
        tsize = (w - 180, int((w - 180) * 0.66))
        tpos = (90, 80)
    elif layout == "right":
        tsize = (520, 780)
        tpos = (w - tsize[0] - 80, 360)
    elif layout == "overlay":
        tsize = (w, h)
        tpos = (0, 0)
    else:  # left default
        tsize = (520, 780)
        tpos = (80, 360)

    thumb = thumb.convert("RGBA").resize(tsize)

    if "rounded" in effects:
        thumb = rounded_image(thumb, 50)

    if "shadow" in effects:
        # simple drop shadow
        shadow = Image.new("RGBA", (tsize[0] + 20, tsize[1] + 20), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        sdraw.rectangle([10, 10, tsize[0] + 10, tsize[1] + 10], fill=(0, 0, 0, 90))
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        canvas.alpha_composite(shadow, (tpos[0] - 10, tpos[1] - 10))

    canvas.alpha_composite(thumb, tpos)

    return canvas


def draw_text_blocks(canvas: Image.Image, data: Dict[str, Any]) -> Image.Image:
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size

    # Font selection
    family, style = data.get("font", ("Roboto", "Regular"))

    # Title
    title_font = get_font(family, style, data.get("title_size", 50))
    title_color = parse_color(data.get("title_color", "#000000"))
    draw.text((60, 40), data.get("name", "Manga Title"), font=title_font, fill=title_color)

    # Author & year line
    author_font = get_font(family, style, data.get("author_size", 35))
    author_color = parse_color(data.get("author_color", "#000000"))
    meta_text = f"By {data.get('author', 'Unknown')}  •  {data.get('year', '')}"
    draw.text((60, 120), meta_text, font=author_font, fill=author_color)

    # Synopsis block
    synopsis_font = get_font(family, style, data.get("synopsis_size", 30))
    synopsis_color = parse_color(data.get("synopsis_color", "#000000"))
    maxw = w - 120
    lines = word_wrap(draw, data.get("synopsis", "No synopsis provided."), synopsis_font, maxw)

    y = 200
    for ln in lines[:12]:
        draw.text((60, y), ln, font=synopsis_font, fill=synopsis_color)
        y += synopsis_font.size + 8

    # Branding top-right
    branding_font = get_font(family, style, data.get("branding_size", 25))
    branding_color = parse_color(data.get("branding_color", "#808080"))
    brand_text = data.get("branding", "waalords")
    bw, bh = draw.textsize(brand_text, font=branding_font)
    draw.text((w - bw - 40, 30), brand_text, font=branding_font, fill=branding_color)

    return canvas


def draw_percentage_box(canvas: Image.Image, data: Dict[str, Any]) -> Image.Image:
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size

    # Settings
    pos = data.get("percentage_box_position", "bottom-right")
    box_w, box_h = 420, 120
    margin = 50

    if pos == "bottom-right":
        x, y = w - box_w - margin, h - box_h - margin
    elif pos == "bottom-left":
        x, y = margin, h - box_h - margin
    elif pos == "top-right":
        x, y = w - box_w - margin, margin
    else:
        x, y = margin, margin

    bg = parse_color(data.get("percentage_box_bg", "#FFFFFF"))
    alpha = int(data.get("percentage_box_alpha", 220))
    border = parse_color(data.get("percentage_box_border", "#000000"))
    radius = int(data.get("percentage_box_radius", 30))

    # Box layer
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle([x, y, x + box_w, y + box_h], radius=radius, fill=(*bg, alpha), outline=border, width=4)
    canvas = Image.alpha_composite(canvas, overlay)

    # Progress circle
    draw = ImageDraw.Draw(canvas)
    cx, cy, r = x + 70, y + box_h // 2, 40
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(200, 200, 200), width=8)
    percent = max(0, min(100, int(data.get("percentage", 0))))
    accent = parse_color(data.get("title_color", "#000000"))
    end_angle = -90 + int(360 * percent / 100)
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=-90, end=end_angle, fill=accent, width=8)

    # Percentage text inside circle
    font_circle = get_font(data.get("font", ("Roboto", "Regular"))[0], "Bold", 26)
    ptxt = f"{percent}%"
    pw, ph = draw.textsize(ptxt, font=font_circle)
    draw.text((cx - pw // 2, cy - ph // 2), ptxt, font=font_circle, fill=accent)

    # Chapters text (optional)
    if data.get("percentage_box_chapters", True):
        font_text = get_font(data.get("font", ("Roboto", "Regular"))[0], "Regular", 28)
        draw.text((cx + 70, cy - 15), f"Ch: {data.get('chapters', '0')}", font=font_text, fill=(0, 0, 0))

    return canvas


def draw_badges(canvas: Image.Image, data: Dict[str, Any]) -> Image.Image:
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    badges = data.get("badges", [])

    # Predefined corner anchors
    anchors = {
        "top-left": (50, 50),
        "top-right": (w - 250, 50),
        "bottom-left": (50, h - 150),
        "bottom-right": (w - 250, h - 150),
    }

    stacks: Dict[str, int] = {k: 0 for k in anchors.keys()}

    for badge in badges[:5]:  # max 5
        pos = badge.get("position", "top-left")
        x0, y0 = anchors.get(pos, anchors["top-left"])
        # stack vertically if multiple in same corner
        y0 += stacks[pos]
        stacks[pos] += 80

        box_w, box_h = int(badge.get("width", 220)), int(badge.get("height", 70))
        bg = parse_color(badge.get("bg", "#FFFFFF"))
        color = parse_color(badge.get("color", "#000000"))
        alpha = int(badge.get("alpha", 220))
        radius = int(badge.get("radius", 20))
        text = badge.get("text", "⭐ Badge")

        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=radius, fill=(*bg, alpha), outline=color, width=2)
        canvas = Image.alpha_composite(canvas, overlay)

        # Text draw
        font = get_font(data.get("font", ("Roboto", "Regular"))[0], "Bold", 28)
        draw = ImageDraw.Draw(canvas)
        draw.text((x0 + 20, y0 + (box_h - 28) // 2), text, font=font, fill=color)

    return canvas


# =============================
# Template variants
# =============================

def render_template(data: Dict[str, Any]) -> Image.Image:
    # Base canvas
    canvas = Image.new("RGBA", CANVAS_SIZE, (255, 255, 255, 255))

    # Background layer
    bg = draw_background(canvas, data)
    canvas = Image.alpha_composite(bg, canvas)

    # If effect includes overall blur on background
    if "blur" in data.get("effects", []):
        canvas = canvas.filter(ImageFilter.GaussianBlur(3))

    # Place thumbnail
    thumb_bytes = data.get("thumbnail")
    if thumb_bytes:
        thumb = Image.open(io.BytesIO(thumb_bytes))
    else:
        # Placeholder gray
        thumb = Image.new("RGB", (600, 900), (200, 200, 200))
    canvas = draw_thumbnail(canvas, thumb, data)

    # Glass/overlay style (for certain template)
    if data.get("template") == "glass":
        overlay = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
        od = ImageDraw.Draw(overlay)
        od.rounded_rectangle([40, 320, CANVAS_SIZE[0] - 40, CANVAS_SIZE[1] - 40], radius=36, fill=(255, 255, 255, 100))
        canvas = Image.alpha_composite(canvas, overlay)

    # Text blocks
    canvas = draw_text_blocks(canvas, data)

    # Percentage box
    canvas = draw_percentage_box(canvas, data)

    # Badges
    canvas = draw_badges(canvas, data)

    return canvas


# =============================
# Telegram Handlers
# =============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s.clear()
    s.update(session(update))  # ensure defaults
    await update.message.reply_text(
        "📸 Send your manga thumbnail image (attach a photo).\nYou can type /cancel anytime."
    )
    return MANGA_IMG


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    SESSIONS.pop(update.effective_chat.id, None)
    await update.message.reply_text("❌ Cancelled. Type /start to begin again.")
    return ConversationHandler.END


async def cmd_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    if "thumbnail" not in s:
        await update.message.reply_text("⚠️ No data yet. Please upload a thumbnail first with /start.")
        return
    img = render_template(s)
    buf = io.BytesIO()
    buf.name = "preview.jpg"
    img.convert("RGB").save(buf, format="JPEG", quality=90)
    buf.seek(0)
    await update.message.reply_photo(photo=InputFile(buf), caption="👀 Live Preview")


async def cmd_colors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Simple color palette image
    sw = 200
    groups = list(COLORS.keys())
    rows = max(len(COLORS[g]) for g in groups)
    img = Image.new("RGB", (sw * len(groups), rows * 60 + 60), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    for gi, g in enumerate(groups):
        d.text((gi * sw + 10, 10), g.upper(), fill="black", font=font)
        for i, (name, hexv) in enumerate(COLORS[g].items()):
            y = 40 + i * 60
            d.rectangle([gi * sw + 10, y, gi * sw + 60, y + 40], fill=hexv, outline="black")
            d.text((gi * sw + 70, y + 10), f"{name} {hexv}", fill="black", font=font)
    buf = io.BytesIO()
    buf.name = "colors.jpg"
    img.save(buf, format="JPEG")
    buf.seek(0)
    await update.message.reply_photo(photo=InputFile(buf), caption="🎨 Some preset colors. You can also type any HEX like #FFAA33.")


async def cmd_fonts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Render sample lines for all fonts & styles
    img = Image.new("RGB", (1200, 2000), "white")
    d = ImageDraw.Draw(img)
    x, y = 30, 20
    for family, styles in FONTS.items():
        d.text((x, y), f"{family}", fill="black", font=ImageFont.load_default())
        y += 30
        for style, file in styles.items():
            try:
                font = ImageFont.truetype(os.path.join("assets", "fonts", file), 36)
            except Exception:
                font = ImageFont.load_default()
            d.text((x + 20, y), f"{style} → Manga Preview", fill="black", font=font)
            y += 52
        y += 16
        if y > 1880:
            break
    buf = io.BytesIO()
    buf.name = "fonts.jpg"
    img.save(buf, format="JPEG")
    buf.seek(0)
    await update.message.reply_photo(photo=InputFile(buf), caption="🔤 Sample of available fonts & styles")


# ========== Step handlers ==========

async def manga_img(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    photo = await update.message.photo[-1].get_file()
    s["thumbnail"] = await photo.download_as_bytearray()
    await update.message.reply_text("🖋️ Enter Manga Name")
    return MANGA_NAME


async def manga_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["name"] = update.message.text.strip()
    await update.message.reply_text("📖 Enter Synopsis")
    return SYNOPSIS


async def synopsis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["synopsis"] = update.message.text.strip()
    await update.message.reply_text("👤 Enter Author name")
    return AUTHOR


async def author(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["author"] = update.message.text.strip()
    await update.message.reply_text("📅 Enter Year (e.g., 2024)")
    return YEAR


async def year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["year"] = update.message.text.strip()
    await update.message.reply_text("📚 Enter Chapters (number)")
    return CHAPTERS


async def chapters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["chapters"] = update.message.text.strip()
    await update.message.reply_text("📊 Enter Completion Percentage (0-100)")
    return PERCENTAGE


async def percentage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    try:
        s["percentage"] = max(0, min(100, int(update.message.text.strip())))
    except Exception:
        s["percentage"] = 0
    await update.message.reply_text("📦 Percentage Box Position (bottom-right, bottom-left, top-right, top-left)")
    return PERCENTAGE_BOX_POSITION


async def percentage_box_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    pos = update.message.text.strip().lower()
    if pos not in ["bottom-right", "bottom-left", "top-right", "top-left"]:
        pos = "bottom-right"
    s["percentage_box_position"] = pos
    await update.message.reply_text("🎨 Percentage Box Background Color (name or HEX, default white). Type /colors to preview.")
    return PERCENTAGE_BOX_BG


async def percentage_box_bg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["percentage_box_bg"] = update.message.text.strip() or "white"
    await update.message.reply_text("🔲 Percentage Box Transparency 0–255 (default 220)")
    return PERCENTAGE_BOX_ALPHA


async def percentage_box_alpha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    try:
        s["percentage_box_alpha"] = int(update.message.text.strip())
    except Exception:
        s["percentage_box_alpha"] = 220
    await update.message.reply_text("⬛ Percentage Box Border Color (default black)")
    return PERCENTAGE_BOX_BORDER


async def percentage_box_border(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["percentage_box_border"] = update.message.text.strip() or "black"
    await update.message.reply_text("◻️ Percentage Box Border Radius (default 30)")
    return PERCENTAGE_BOX_RADIUS


async def percentage_box_radius(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    try:
        s["percentage_box_radius"] = int(update.message.text.strip())
    except Exception:
        s["percentage_box_radius"] = 30
    await update.message.reply_text("📖 Show Chapters inside box? (yes/no, default yes)")
    return PERCENTAGE_BOX_CHAPTERS


async def percentage_box_chapters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    ans = update.message.text.strip().lower()
    s["percentage_box_chapters"] = ans != "no"
    await update.message.reply_text(
        "🏷️ Do you want to add badges? (yes/no)\nYou can always add more later with /addbadge"
    )
    return BADGE_START


async def badge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    if update.message.text.strip().lower() == "yes":
        s.setdefault("badges", [])
        await update.message.reply_text("✨ Enter badge text (e.g., ⭐ Top 10, 🔥 Trending). Or type 'done' to finish.")
        return BADGE_TEXT
    else:
        await update.message.reply_text(
            "🖼️ Choose Template: classic / modern / glass / poster"
        )
        return TEMPLATE


async def badge_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    txt = update.message.text.strip()
    if txt.lower() == "done":
        await update.message.reply_text("🖼️ Choose Template: classic / modern / glass / poster")
        return TEMPLATE
    badge = {"text": txt}
    s.setdefault("badges", []).append(badge)
    await update.message.reply_text("🎨 Badge background color (default white)")
    return BADGE_BG


async def badge_bg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["badges"][-1]["bg"] = update.message.text.strip() or "white"
    await update.message.reply_text("🎨 Badge text color (default black)")
    return BADGE_TEXT_COLOR


async def badge_text_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["badges"][-1]["color"] = update.message.text.strip() or "black"
    await update.message.reply_text("🔲 Badge transparency 0–255 (default 220)")
    return BADGE_ALPHA


async def badge_alpha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    try:
        s["badges"][-1]["alpha"] = int(update.message.text.strip())
    except Exception:
        s["badges"][-1]["alpha"] = 220
    await update.message.reply_text("◻️ Badge border radius (default 20)")
    return BADGE_RADIUS


async def badge_radius(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    try:
        s["badges"][-1]["radius"] = int(update.message.text.strip())
    except Exception:
        s["badges"][-1]["radius"] = 20
    await update.message.reply_text("📍 Badge position (top-left, top-right, bottom-left, bottom-right)")
    return BADGE_POSITION


async def badge_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    pos = update.message.text.strip().lower()
    if pos not in ["top-left", "top-right", "bottom-left", "bottom-right"]:
        pos = "top-left"
    s["badges"][-1]["position"] = pos
    await update.message.reply_text("✨ Enter another badge text or type 'done' to finish.")
    return BADGE_TEXT


async def template_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    t = update.message.text.strip().lower()
    if t not in ["classic", "modern", "glass", "poster"]:
        t = "classic"
    s["template"] = t
    await update.message.reply_text(
        "🌆 Background type: solid / gradient / pattern / image\n(If image, upload next message.)"
    )
    return BACKGROUND_TYPE


async def background_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    b = update.message.text.strip().lower()
    if b not in ["solid", "gradient", "pattern", "image"]:
        b = "solid"
    s["background_type"] = b
    if b == "solid":
        await update.message.reply_text("🎨 Background color (name or HEX, default white)")
        return BACKGROUND_DETAIL
    elif b == "gradient":
        await update.message.reply_text("🎨 Enter two colors separated by comma (e.g., #FF512F,#DD2476)")
        return BACKGROUND_DETAIL
    elif b == "pattern":
        await update.message.reply_text("🎨 Pattern style: stripes / dots / noise\n(Optional) Then provide bg,fg colors like: stripes,#111111,#333333")
        return BACKGROUND_DETAIL
    else:  # image
        await update.message.reply_text("📤 Upload background image now")
        return BACKGROUND_DETAIL


async def background_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    if s.get("background_type") == "solid":
        s["background_color"] = update.message.text.strip() or "white"
    elif s.get("background_type") == "gradient":
        parts = [p.strip() for p in update.message.text.split(",") if p.strip()]
        if len(parts) >= 2:
            s["background_colors"] = parts[:2]
        else:
            s["background_colors"] = ["#000000", "#FFFFFF"]
    elif s.get("background_type") == "pattern":
        parts = [p.strip() for p in update.message.text.split(",") if p.strip()]
        style = parts[0] if parts else "stripes"
        s["pattern_style"] = style
        if len(parts) >= 3:
            s["pattern_bg"], s["pattern_fg"] = parts[1], parts[2]
        else:
            s["pattern_bg"], s["pattern_fg"] = "#111111", "#222222"
    elif s.get("background_type") == "image" and update.message.photo:
        photo = await update.message.photo[-1].get_file()
        s["background_image"] = await photo.download_as_bytearray()
    await update.message.reply_text("📐 Layout: left / right / top / overlay")
    return LAYOUT


async def layout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    lay = update.message.text.strip().lower()
    if lay not in ["left", "right", "top", "overlay"]:
        lay = "left"
    s["layout"] = lay
    await update.message.reply_text("✨ Effects (comma separated): rounded,shadow,blur or 'none'")
    return EFFECTS


async def effects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    txt = update.message.text.strip().lower()
    if txt == "none":
        s["effects"] = []
    else:
        s["effects"] = [t.strip() for t in txt.split(",") if t.strip() in ["rounded", "shadow", "blur"]]
    await update.message.reply_text("💾 Export format: jpg / png / pdf")
    return EXPORT_FORMAT


async def export_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    fmt = update.message.text.strip().lower()
    if fmt not in ["jpg", "png", "pdf"]:
        fmt = "jpg"
    s["export"] = fmt
    await update.message.reply_text("🏷️ Branding text (e.g., waalords)")
    return BRANDING


async def branding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["branding"] = update.message.text.strip() or "waalords"
    await update.message.reply_text("🔤 Choose font (family and style) like: Roboto Bold. Use /fonts to preview.")
    return FONT_FAMILY_STYLE


async def font_family_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    parts = update.message.text.strip().split()
    family = parts[0] if parts else "Roboto"
    style = parts[1] if len(parts) > 1 else "Regular"
    if family not in FONTS or style not in FONTS.get(family, {}):
        family, style = "Roboto", "Regular"
    s["font"] = (family, style)
    await update.message.reply_text("🔠 Title Font Size (default 50)")
    return TITLE_SIZE


async def title_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    try:
        s["title_size"] = int(update.message.text.strip())
    except Exception:
        s["title_size"] = 50
    await update.message.reply_text("✍️ Author Font Size (default 35)")
    return AUTHOR_SIZE


async def author_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    try:
        s["author_size"] = int(update.message.text.strip())
    except Exception:
        s["author_size"] = 35
    await update.message.reply_text("📖 Synopsis Font Size (default 30)")
    return SYNOPSIS_SIZE


async def synopsis_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    try:
        s["synopsis_size"] = int(update.message.text.strip())
    except Exception:
        s["synopsis_size"] = 30
    await update.message.reply_text("🏷️ Branding Font Size (default 25)")
    return BRANDING_SIZE


async def branding_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    try:
        s["branding_size"] = int(update.message.text.strip())
    except Exception:
        s["branding_size"] = 25
    await update.message.reply_text("🎨 Title Color (name or HEX, default black). Use /colors to preview presets.")
    return TITLE_COLOR


async def title_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["title_color"] = update.message.text.strip() or "black"
    await update.message.reply_text("🎨 Author Color (default black)")
    return AUTHOR_COLOR


async def author_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["author_color"] = update.message.text.strip() or "black"
    await update.message.reply_text("🎨 Synopsis Color (default black)")
    return SYNOPSIS_COLOR


async def synopsis_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["synopsis_color"] = update.message.text.strip() or "black"
    await update.message.reply_text("🎨 Branding Color (default gray)")
    return BRANDING_COLOR


async def branding_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["branding_color"] = update.message.text.strip() or "gray"

    # Final render and send
    img = render_template(s)
    buf = io.BytesIO()
    fmt = s.get("export", "jpg").upper()
    if fmt == "PDF":
        buf.name = "manga_card.pdf"
        img.convert("RGB").save(buf, format="PDF")
        buf.seek(0)
        await update.message.reply_document(InputFile(buf))
    elif fmt == "PNG":
        buf.name = "manga_card.png"
        img.save(buf, format="PNG")
        buf.seek(0)
        await update.message.reply_photo(photo=InputFile(buf), caption="✅ Final Manga Card")
    else:
        buf.name = "manga_card.jpg"
        img.convert("RGB").save(buf, format="JPEG", quality=92)
        buf.seek(0)
        await update.message.reply_photo(photo=InputFile(buf), caption="✅ Final Manga Card")

    return ConversationHandler.END


# Extra commands for badges management
async def cmd_addbadge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Shortcut to start badge adding outside main flow
    s = session(update)
    s.setdefault("badges", [])
    await update.message.reply_text("✨ Enter badge text (e.g., ⭐ Top 10). Type 'cancel' to stop.")
    return BADGE_TEXT


async def cmd_clearbadges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = session(update)
    s["badges"] = []
    await update.message.reply_text("🧹 Cleared all badges.")


# =============================
# App Bootstrap
# =============================

def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MANGA_IMG: [MessageHandler(filters.PHOTO, manga_img)],
            MANGA_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, manga_name)],
            SYNOPSIS: [MessageHandler(filters.TEXT & ~filters.COMMAND, synopsis)],
            AUTHOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, author)],
            YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, year)],
            CHAPTERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, chapters)],
            PERCENTAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, percentage)],

            PERCENTAGE_BOX_POSITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, percentage_box_position)],
            PERCENTAGE_BOX_BG: [MessageHandler(filters.TEXT & ~filters.COMMAND, percentage_box_bg)],
            PERCENTAGE_BOX_ALPHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, percentage_box_alpha)],
            PERCENTAGE_BOX_BORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, percentage_box_border)],
            PERCENTAGE_BOX_RADIUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, percentage_box_radius)],
            PERCENTAGE_BOX_CHAPTERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, percentage_box_chapters)],

            BADGE_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, badge_start)],
            BADGE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, badge_text)],
            BADGE_BG: [MessageHandler(filters.TEXT & ~filters.COMMAND, badge_bg)],
            BADGE_TEXT_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, badge_text_color)],
            BADGE_ALPHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, badge_alpha)],
            BADGE_RADIUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, badge_radius)],
            BADGE_POSITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, badge_position)],

            TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_pick)],
            BACKGROUND_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, background_type)],
            BACKGROUND_DETAIL: [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, background_detail)],
            LAYOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, layout)],
            EFFECTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, effects)],
            EXPORT_FORMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, export_format)],
            BRANDING: [MessageHandler(filters.TEXT & ~filters.COMMAND, branding)],

            FONT_FAMILY_STYLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, font_family_style)],
            TITLE_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, title_size)],
            AUTHOR_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, author_size)],
            SYNOPSIS_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, synopsis_size)],
            BRANDING_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, branding_size)],
            TITLE_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, title_color)],
            AUTHOR_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, author_color)],
            SYNOPSIS_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, synopsis_color)],
            BRANDING_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, branding_color)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("preview", cmd_preview))
    app.add_handler(CommandHandler("colors", cmd_colors))
    app.add_handler(CommandHandler("fonts", cmd_fonts))
    app.add_handler(CommandHandler("addbadge", cmd_addbadge))
    app.add_handler(CommandHandler("clearbadges", cmd_clearbadges))

    return app


def main():
    app = build_app()
    print("Bot starting…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
