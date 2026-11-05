"""Extract design tokens from the Shattered Pixel Dungeon source tree.

Usage: python3 -I tools/extract.py <path-to-shattered-pixel-dungeon>
Writes tokens.json and tokens.js next to index.html.
Only values that are mechanically parsed live here; curated notes live in app.js.
"""
import base64, json, re, subprocess, sys
from pathlib import Path

SRC = Path(sys.argv[1]).resolve()
OUT = Path(__file__).resolve().parent.parent
C = SRC / "core/src/main/java/com/shatteredpixel/shatteredpixeldungeon"
ASSETS = SRC / "core/src/main/assets"


def rel(p):
    return str(p.relative_to(SRC))


def int_consts(path, names=None):
    """public static final int NAME = 0x...; -> [{name, hex, alpha, src}]"""
    out = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        m = re.search(r"static final int\s+(\w+)\s*=\s*0x([0-9A-Fa-f]{6,8})\s*;", line)
        if m and (names is None or m.group(1) in names):
            h = m.group(2).upper()
            alpha = round(int(h[:2], 16) / 255, 2) if len(h) == 8 else 1
            out.append({"name": m.group(1), "hex": "#" + h[-6:], "alpha": alpha,
                        "src": f"{rel(path)}:{i}"})
    return out


def chrome_types():
    path = C / "Chrome.java"
    lines = path.read_text().splitlines()
    out, pending = [], []
    for i, line in enumerate(lines, 1):
        if m := re.match(r"\s*case (\w+):", line):
            pending.append(m.group(1))
        elif m := re.search(r"new NinePatch\(\s*Asset,\s*([\d,\s]+)\)", line):
            n = [int(v) for v in m.group(1).split(",")]
            x, y, w, h, *mg = n
            mg = mg * 4 if len(mg) == 1 else mg
            for name in pending:
                out.append({"name": name, "rect": [x, y, w, h], "margins": mg,
                            "src": f"{rel(path)}:{i}"})
            pending = []
    return out


def icons():
    path = C / "ui/Icons.java"
    out, pending = [], []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if m := re.match(r"\s*case (\w+):", line):
            pending.append(m.group(1))
        elif m := re.search(r"uvRectBySize\(\s*([\d\s,]+)\)", line):
            x, y, w, h = [int(v) for v in m.group(1).split(",")]
            for name in pending:
                out.append({"name": name, "rect": [x, y, w, h], "src": f"{rel(path)}:{i}"})
            pending = []
        elif "return" in line or "break" in line:
            if "return get(" in line:
                pending = []
    return out


def buffs():
    path = C / "ui/BuffIndicator.java"
    out = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        m = re.search(r"public static final int\s+(\w+)\s*=\s*(\d+)\s*;", line)
        if m and m.group(1) != "NONE" and not m.group(1).startswith("SIZE_"):
            out.append({"name": m.group(1), "index": int(m.group(2)), "src": f"{rel(path)}:{i}"})
    return out


def float_consts(path, names):
    out = {}
    for i, line in enumerate(path.read_text().splitlines(), 1):
        m = re.search(r"static final float\s+(\w+)\s*=\s*([\d.]+)f?\s*;", line)
        if m and m.group(1) in names:
            out[m.group(1)] = {"value": float(m.group(2)), "src": f"{rel(path)}:{i}"}
    return out


def text_sizes():
    """Tally literal sizes passed to PixelScene.renderTextBlock(...); the size is the last argument."""
    tally = {}
    for p in C.rglob("*.java"):
        for stmt in re.findall(r"renderTextBlock\((.*?)\)\s*;", p.read_text()):
            m = re.search(r"(?:^|,)\s*(\d+)\s*$", stmt)
            key = int(m.group(1)) if m else "variable"
            tally[key] = tally.get(key, 0) + 1
    return dict(sorted(tally.items(), key=lambda kv: (isinstance(kv[0], str), kv[0])))


def layout_tally(pattern):
    """Tally `NAME = <int>` declarations across windows/, ui/ and scenes/."""
    tally = {}
    for d in ("windows", "ui", "scenes"):
        for p in (C / d).rglob("*.java"):
            for m in re.finditer(pattern, p.read_text()):
                tally[int(m.group(1))] = tally.get(int(m.group(1)), 0) + 1
    return dict(sorted(tally.items()))


def commit():
    out = subprocess.run(["git", "-C", str(SRC), "log", "-1", "--format=%H %cs"],
                         capture_output=True, text=True, check=True).stdout.split()
    return {"hash": out[0], "date": out[1]}


version = re.search(r"appVersionName = '([^']+)'", (SRC / "build.gradle").read_text()).group(1)

tokens = {
    "meta": {"game": "Shattered Pixel Dungeon", "version": version, "commit": commit()},
    "colors": {
        "window": int_consts(C / "ui/Window.java"),
        "charSprite": int_consts(C / "sprites/CharSprite.java"),
        "itemSlot": int_consts(C / "ui/ItemSlot.java"),
        "healthBar": int_consts(C / "ui/HealthBar.java"),
    },
    "chrome": {"asset": "assets/chrome.png", "size": [128, 64], "types": chrome_types()},
    "icons": {"asset": "assets/icons.png", "size": [256, 128], "items": icons()},
    "buffs": {"small": {"asset": "assets/buffs.png", "cell": 7, "size": [128, 64]},
              "large": {"asset": "assets/large_buffs.png", "cell": 16, "size": [256, 128]},
              "items": buffs()},
    "screen": float_consts(C / "scenes/PixelScene.java",
                           {"MIN_WIDTH_P", "MIN_HEIGHT_P", "MIN_WIDTH_L", "MIN_HEIGHT_L",
                            "MIN_WIDTH_FULL", "MIN_HEIGHT_FULL"}),
    "textSizeTally": text_sizes(),
    "layoutTally": {
        "gap": layout_tally(r"\bGAP\s*=\s*(\d+)\s*;"),
        "margin": layout_tally(r"\bMARGIN\s*=\s*(\d+)\s*;"),
        "windowWidth": layout_tally(r"\bWIDTH(?:_P|_L)?\s*=\s*(\d+)\s*;"),
        "buttonHeight": layout_tally(r"\b(?:BTN|BUTTON)_HEIGHT\s*=\s*(\d+)\s*;"),
    },
}

(OUT / "tokens.json").write_text(json.dumps(tokens, indent=2, ensure_ascii=False) + "\n")
chrome_b64 = base64.b64encode((ASSETS / "interfaces/chrome.png").read_bytes()).decode()
# chrome.png is embedded so canvas cropping also works when index.html is opened via file://
(OUT / "tokens.js").write_text(
    "// Generated by tools/extract.py. Do not edit by hand.\n"
    f"window.SPD = {json.dumps(tokens, ensure_ascii=False)};\n"
    f"window.SPD_CHROME_PNG = 'data:image/png;base64,{chrome_b64}';\n")

print(f"v{version} {tokens['meta']['commit']['hash'][:7]}: {tokens['layoutTally']}\n"
      f"{sum(len(v) for v in tokens['colors'].values())} colors, {len(tokens['chrome']['types'])} chrome, "
      f"{len(tokens['icons']['items'])} icons, {len(tokens['buffs']['items'])} buffs, "
      f"text sizes {tokens['textSizeTally']}")
