"""Extract melee weapons, armor, enchantments and glyphs from the Shattered Pixel Dungeon source.

Usage (from the site dir): python3 -I tools/extract_gear.py ../shattered-pixel-dungeon
Writes data/gear.json and data/gear.js (window.SPD_GEAR = {...};).
Every value carries "src": "path:line" relative to the SPD repo root, or is flagged as judgment.
Not modelled in DPT: enchantments, talents, rings, Duelist abilities, surprise attacks, blocking.
"""
import json, math, re, sys
from pathlib import Path

SRC = Path(sys.argv[1]).resolve()
OUT = Path(__file__).resolve().parent.parent / "data"
C = SRC / "core/src/main/java/com/shatteredpixel/shatteredpixeldungeon"
ASSETS = SRC / "core/src/main/assets"
KO = ASSETS / "messages/items/items_ko.properties"
EN = ASSETS / "messages/items/items.properties"
ACTORS_KO = ASSETS / "messages/actors/actors_ko.properties"


def rel(p):
    return str(Path(p).relative_to(SRC))


def loc(path, pattern, start=1):
    """'path:line' of the first line >= start matching pattern; raises if absent so srcs never rot."""
    for i, line in enumerate(Path(path).read_text().splitlines(), 1):
        if i >= start and re.search(pattern, line):
            return f"{rel(path)}:{i}"
    raise SystemExit(f"loc: /{pattern}/ not found in {path}")


def props(path):
    out = {}
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = (v.strip(), i)
    return out


KOP, ENP, ACP = props(KO), props(EN), props(ACTORS_KO)


def msg(table, path, key):
    """-> {'text','src'} or None"""
    if key not in table:
        return None
    v, i = table[key]
    return {"text": v, "src": f"{rel(path)}:{i}"}


def jround(x):  # java Math.round
    return math.floor(x + 0.5)


def strip_comments(s):
    return re.sub(r"//[^\n]*", "", s)


def java_eval(expr, **names):
    e = strip_comments(expr).replace("Math.round", "jround").replace("Math.max", "max")
    e = re.sub(r"(?<=[\d.])f\b", "", e)
    e = " ".join(e.split())
    if re.search(r"[^\w\s.+\-*/()%,]", e):
        raise ValueError(f"unsafe expr {expr!r}")
    return eval(e, {"__builtins__": {}}, {"jround": jround, "max": max, **names})


# ---------------------------------------------------------------- sprites
SHEET = C / "sprites/ItemSpriteSheet.java"
SHEET_TXT = SHEET.read_text()
SHEET_SIZE = int(re.search(r"int SIZE = (\d+);", SHEET_TXT).group(1))
TX_W = int(re.search(r"TX_WIDTH = (\d+);", SHEET_TXT).group(1))
TX_H = int(re.search(r"TX_HEIGHT = (\d+);", SHEET_TXT).group(1))
GRID_W = TX_W // SHEET_SIZE
_consts = {m.group(1): m.group(2).strip() for m in
           re.finditer(r"static final int (\w+)\s*=\s*([^;/]+?)\s*(?://[^\n]*)?;", SHEET_TXT)}


def sprite_index(name):
    expr = _consts[name]
    if m := re.fullmatch(r"xy\((\d+),\s*(\d+)\)", expr):
        return int(m.group(1)) - 1 + GRID_W * (int(m.group(2)) - 1)
    a, b = re.fullmatch(r"(\w+)\s*\+\s*(\d+)", expr).groups()
    return sprite_index(a) + int(b)


def sprite_rect(name):
    idx = sprite_index(name)
    m = re.search(rf"assignItemRect\(\s*{name}\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", SHEET_TXT)
    return {"name": name, "x": idx % GRID_W * SHEET_SIZE, "y": idx // GRID_W * SHEET_SIZE,
            "w": int(m.group(1)), "h": int(m.group(2)),
            "src": loc(SHEET, rf"assignItemRect\(\s*{name}\s*,")}


def png_size(p):
    b = p.read_bytes()
    return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")


ITEMS_PNG = ASSETS / "sprites/items.png"
W, H = png_size(ITEMS_PNG)
assert (W, H) == (TX_W, TX_H), "items.png size no longer matches ItemSpriteSheet TX_WIDTH/HEIGHT"
SPRITES = {"asset": "sprites/items.png", "width": W, "height": H, "bytes": ITEMS_PNG.stat().st_size,
           "cell": SHEET_SIZE, "gridWidth": GRID_W,
           "rule": "index = (x-1)+16*(y-1) for xy(x,y); rect = (index%16*16, index//16*16, w, h) "
                   "from assignItemRect(NAME,w,h)",
           "src": loc(SHEET, r"private static void assignItemRect")}


# ---------------------------------------------------------------- shared formulas
def str_req(tier, lvl):
    lvl = max(0, lvl)
    return (8 + tier * 2) - int(math.sqrt(8 * lvl + 1) - 1) // 2


WEAPON_JAVA = C / "items/weapon/Weapon.java"
ARMOR_JAVA = C / "items/armor/Armor.java"
HERO_JAVA = C / "actors/hero/Hero.java"
MELEE_DIR = C / "items/weapon/melee"
MELEE_BASE = MELEE_DIR / "MeleeWeapon.java"

# one-line notes for every overridden combat method, keyed (class, method). Loud failure if a new override appears.
OVERRIDE_NOTES = {
    ("AssassinsBlade", "damageRoll"): "Surprise attack: roll from 50% toward max up to max instead of min..max (+ excess-STR bonus).",
    ("Dagger", "damageRoll"): "Surprise attack: roll from 75% toward max up to max instead of min..max (+ excess-STR bonus).",
    ("Dirk", "damageRoll"): "Surprise attack: roll from 67% toward max up to max instead of min..max (+ excess-STR bonus).",
    ("Crossbow", "accuracyFactor"): "Only with the Charged Shot ability buff: infinite accuracy.",
    ("Crossbow", "proc"): "Only with the Charged Shot ability buff: knocks the target back 4 tiles.",
    ("Flail", "damageRoll"): "Adds spinBoost (Spin ability only; 0 on normal attacks).",
    ("Flail", "accuracyFactor"): "Spin ability: infinite accuracy and +(8+2*lvl) per spin; normal attacks use ACC 0.8.",
    ("Greataxe", "STRReq"): "STR requirement uses tier+1 (20 at +0 instead of 18).",
    ("Greatshield", "defenseFactor"): "Blocking weapon: Hero.drRoll adds NormalIntRange(0, 6+2*lvl) damage reduction while equipped.",
    ("Greatshield", "DRMax"): "Defines the 6+2*lvl block value used by defenseFactor.",
    ("RoundShield", "defenseFactor"): "Blocking weapon: Hero.drRoll adds NormalIntRange(0, 4+lvl) damage reduction while equipped.",
    ("RoundShield", "DRMax"): "Defines the 4+lvl block value used by defenseFactor.",
    ("Katana", "defenseFactor"): "Blocking weapon: Hero.drRoll adds NormalIntRange(0, 3) damage reduction while equipped.",
    ("Quarterstaff", "defenseFactor"): "Blocking weapon: Hero.drRoll adds NormalIntRange(0, 2) damage reduction while equipped.",
    ("Rapier", "defenseFactor"): "Blocking weapon: Hero.drRoll adds NormalIntRange(0, 1) damage reduction while equipped.",
    ("MagesStaff", "proc"): "Talent/Battlemage on-hit effects (wand onHit, Empowered Strike); no change to base damage.",
    ("MagesStaff", "reachFactor"): "Battlemage with Wand of Disintegration gains extra reach.",
}
COMBAT_METHODS = {"damageRoll", "accuracyFactor", "proc", "defenseFactor", "reachFactor", "STRReq",
                  "baseDelay", "speedMultiplier", "delayFactor", "canReach", "DRMax", "min"}


def starter_map():
    path, cur, out = C / "actors/hero/HeroClass.java", None, {}
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if m := re.search(r"private static void init(\w+)\(", line):
            cur = m.group(1)
        for m in re.finditer(r"new (WornShortsword|Dagger|Gloves|MagesStaff|Rapier|Cudgel)\(", line):
            out.setdefault(m.group(1), {"hero": cur, "src": f"{rel(path)}:{i}"})
    return out


def melee_weapons():
    starters = starter_map()
    base_txt = MELEE_BASE.read_text()
    assert re.search(r"public int min\(int lvl\) \{\s*return\s+tier \+\s*//base\s*lvl;", base_txt), "MeleeWeapon.min changed"
    assert not any(re.search(r"int min\(int lvl\)", p.read_text()) for p in MELEE_DIR.glob("*.java") if p != MELEE_BASE), \
        "a melee weapon now overrides min(); coefficients below assume tier+lvl"
    out = []
    for p in sorted(MELEE_DIR.glob("*.java")):
        txt = p.read_text()
        m = re.search(r"public class (\w+) extends MeleeWeapon", txt)
        if not m or p == MELEE_BASE:
            continue
        cls = m.group(1)
        key = f"items.weapon.melee.{cls.lower()}"
        tier = int(re.search(r"\btier\s*=\s*(\d+)\s*;", txt).group(1))
        w = {"id": cls, "src": rel(p), "tier": tier, "tierSrc": loc(p, r"\btier\s*=\s*\d+;")}
        w["name"] = {"ko": msg(KOP, KO, key + ".name"), "en": msg(ENP, EN, key + ".name")}

        # damage coefficients
        mm = re.search(r"public int max\(int lvl\)\s*\{(.*?)\}", txt, re.S)
        if mm:
            body = re.search(r"return(.*?);", strip_comments(mm.group(1)), re.S).group(1)
            max_src, max_expr = loc(p, r"public int max\(int lvl\)"), " ".join(body.split())
        else:
            body = "5*(tier+1) + lvl*(tier+1)"
            max_src, max_expr = loc(MELEE_BASE, r"public int max\(int lvl\)"), body + " [MeleeWeapon default]"
        f = lambda l: java_eval(body, tier=tier, lvl=l)
        b, s = f(0), f(1) - f(0)
        assert f(2) - b == 2 * s and f(7) - b == 7 * s, f"{cls}: max() is not linear in lvl"
        w["damage"] = {"minBase": tier, "minPerLvl": 1, "maxBase": b, "maxPerLvl": s,
                       "maxExpr": max_expr, "maxSrc": max_src,
                       "minSrc": loc(MELEE_BASE, r"public int min\(int lvl\)"),
                       "overridesMax": bool(mm)}

        # ACC / DLY / RCH
        for fld, default, cast in (("ACC", 1.0, float), ("DLY", 1.0, float), ("RCH", 1, int)):
            fm = re.search(rf"\b{fld}\s*=\s*([\d.]+)f?\s*;", txt)
            w[fld] = {"value": cast(fm.group(1)) if fm else default,
                      "src": loc(p if fm else WEAPON_JAVA, rf"\b{fld}\s*=")}

        # defenseFactor (blocking weapons)
        dm = re.search(r"public int defenseFactor\( Char owner \)\s*\{\s*return\s*(.*?);", txt, re.S)
        if dm:
            r = dm.group(1).strip()
            if r == "DRMax()":
                dd = re.search(r"public int DRMax\(int lvl\)\s*\{\s*return\s*(.*?);", txt, re.S).group(1)
                base, per = java_eval(dd, lvl=0), java_eval(dd, lvl=1) - java_eval(dd, lvl=0)
                w["defenseFactor"] = {"base": base, "perLvl": per, "expr": dd, "src": loc(p, r"public int DRMax\(int lvl\)")}
            else:
                w["defenseFactor"] = {"base": int(r), "perLvl": 0, "expr": r, "src": loc(p, r"public int defenseFactor")}
            w["defenseFactor"]["usedBy"] = loc(HERO_JAVA, r"belongings\.weapon\(\)\.defenseFactor")
        else:
            w["defenseFactor"] = None

        # STR req
        s_tier = tier + 1 if re.search(r"STRReq\(tier\+1,\s*lvl\)", txt) else tier
        w["strReq"] = {"tierUsed": s_tier, "base": 8 + 2 * s_tier, "byLevel": [str_req(s_tier, l) for l in range(0, 13)],
                       "formula": "(8 + 2*tierUsed) - (int)(sqrt(8*lvl+1)-1)/2",
                       "src": loc(WEAPON_JAVA, r"protected static int STRReq\(int tier"),
                       "overrideSrc": loc(p, r"public int STRReq") if s_tier != tier else None}

        # other overridden combat methods
        ov = []
        for om in re.finditer(r"^\t(?:public|protected) [\w<>?]+ (\w+)\(", txt, re.M):
            name = om.group(1)
            if name in COMBAT_METHODS:
                note = OVERRIDE_NOTES.get((cls, name))
                assert note, f"unreviewed override {cls}.{name} - add it to OVERRIDE_NOTES"
                ov.append({"method": name, "note": note, "src": loc(p, rf"\b{name}\(")})
        w["overrides"] = ov
        w["notes"] = [o["note"] for o in ov]
        if w["RCH"]["value"] > 1:
            w["notes"].append(f"Reach {w['RCH']['value']} tiles (not in DPT).")
        w["classStart"] = starters.get(cls)

        # Duelist ability (ko strings keep their %d/%1$d placeholders; the game fills them from level)
        w["ability"] = {"name": msg(KOP, KO, key + ".ability_name"),
                        "desc": msg(KOP, KO, key + ".ability_desc"),
                        "typicalDesc": msg(KOP, KO, key + ".typical_ability_desc")}
        w["desc"] = msg(KOP, KO, key + ".desc")
        w["statsDesc"] = msg(KOP, KO, key + ".stats_desc")
        w["sprite"] = sprite_rect(re.search(r"image = ItemSpriteSheet\.(\w+);", txt).group(1))
        out.append(w)
    return out


# ---------------------------------------------------------------- DPT
def normal_int_pmf(lo, hi):
    """Random.NormalIntRange: lo + (int)((u1+u2)*(hi-lo+1)/2) -> triangular pmf."""
    n = hi - lo + 1
    F = lambda s: s * s / 2 if s <= 1 else 1 - (2 - s) ** 2 / 2
    return {lo + k: F(2 * (k + 1) / n) - F(2 * k / n) for k in range(n)}


def convolve(a, b):
    out = {}
    for x, px in a.items():
        for y, py in b.items():
            out[x + y] = out.get(x + y, 0) + px * py
    return out


def p_hit(acc, dfn):
    """Char.hit: acuRoll=Float(acc), defRoll=Float(def); hit if acu>=def."""
    if dfn <= 0:
        return 1.0
    return 1 - dfn / (2 * acc) if acc >= dfn else acc / (2 * dfn)


def dpt(w, lvl, hero_str, attack_skill, mob_def, mob_dr_max, str_mode):
    d = w["damage"]
    req = str_req(w["strReq"]["tierUsed"], lvl)
    strength = req if str_mode == "atReq" else hero_str
    enc = req - strength
    ex = strength - req
    lo, hi = d["minBase"] + d["minPerLvl"] * lvl, d["maxBase"] + d["maxPerLvl"] * lvl
    pmf = normal_int_pmf(lo, hi)
    if ex > 0:
        pmf = convolve(pmf, normal_int_pmf(0, ex))
    raw = sum(k * p for k, p in pmf.items())
    drp = normal_int_pmf(0, mob_dr_max)
    after = sum(p * q * max(k - r, 0) for k, p in pmf.items() for r, q in drp.items())
    acc_factor = w["ACC"]["value"] / (1.5 ** enc) if enc > 0 else w["ACC"]["value"]
    acc = max(1, jround(attack_skill * acc_factor))
    delay = w["DLY"]["value"] * (1.2 ** enc if enc > 0 else 1)
    ph = p_hit(acc, mob_def)
    return {"min": lo, "max": hi, "strReq": req, "heroStr": strength, "excessStr": max(ex, 0), "shortfall": max(enc, 0),
            "avgRawDamage": round(raw, 3), "avgDamageAfterDR": round(after, 3), "attackSkill": acc,
            "pHit": round(ph, 4), "delay": round(delay, 4), "dpt": round(ph * after / delay, 4)}


def scenarios(weapons):
    brute, golem = C / "actors/mobs/Brute.java", C / "actors/mobs/Golem.java"
    spawner = C / "actors/mobs/MobSpawner.java"
    charj = C / "actors/Char.java"
    mobs = {}
    for mid, path, dr, rot, depth in (("brute", brute, 8, r"2x bat, 2x brute", 12), ("golem", golem, 12, r"3x golem", 20)):
        t = path.read_text()
        assert "defenseSkill = 15;" in t and f"NormalIntRange(0, {dr})" in t, f"{mid} stats changed"
        mobs[mid] = {"name": msg(ACP, ACTORS_KO, f"actors.mobs.{mid}.name"), "depth": depth,
                     "defenseSkill": 15, "defenseSrc": loc(path, r"defenseSkill = 15;"),
                     "drRoll": f"Char.drRoll (Barkskin, 0 here) + NormalIntRange(0, {dr})", "drMax": dr,
                     "drSrc": loc(path, rf"NormalIntRange\(0, {dr}\)"),
                     "depthSrc": loc(spawner, rot)}
    dmg_roll_pat = r"public int damageRoll\(\)"
    src = {
        "attackSkill": "base 10 " + loc(HERO_JAVA, r"private int attackSkill = 10") + ", +1 per level-up "
                       + loc(HERO_JAVA, r"attackSkill\+\+") + ", lvl starts at 1 " + loc(HERO_JAVA, r"public int lvl = 1")
                       + "; Hero.attackSkill " + loc(HERO_JAVA, r"public int attackSkill") + " multiplies by weapon.accuracyFactor",
        "accuracyFactor": loc(WEAPON_JAVA, r"public float accuracyFactor") + ": ACC / 1.5^(STRReq-STR) when STR is short",
        "delay": loc(WEAPON_JAVA, r"protected float baseDelay") + ": DLY * 1.2^(STRReq-STR) when STR is short; Hero.attackDelay "
                 + loc(HERO_JAVA, r"public float attackDelay"),
        "damageRoll": "Hero.damageRoll " + loc(HERO_JAVA, dmg_roll_pat) + " -> MeleeWeapon.damageRoll "
                      + loc(MELEE_BASE, r"public int damageRoll") + ": NormalIntRange(min,max) + NormalIntRange(0, STR-STRReq) "
                      + "when STR exceeds req; KindOfWeapon.damageRoll " + loc(C / "items/KindOfWeapon.java", r"heroDamageIntRange"),
        "hit": "Char.hit " + loc(charj, r"float acuRoll = Random.Float") + ": acu>=def with uniform rolls -> P=1-d/(2a) if a>=d else a/(2d)",
        "dr": "Char.attack " + loc(charj, r"int dr = Math.round\(enemy.drRoll") + " then max(dmg-dr,0) "
              + loc(charj, r"Math.max\(effectiveDamage - dr, 0\)"),
        "strPotions": loc(C / "Dungeon.java", r"public static boolean posNeeded") + ": 2 potions of strength per 5 floors; start STR "
                      + loc(HERO_JAVA, r"STARTING_STR = 10"),
        "normalIntRange": loc(SRC / "SPD-classes/src/main/java/com/watabou/utils/Random.java", r"public static int NormalIntRange"),
    }
    defs = [
        {"id": "A", "label_ko": "중반: 영웅 Lv10, 무기 +0, 힘 14, 12층 브루트", "heroLevel": 10, "weaponLevel": 0, "heroStr": 14,
         "strMode": "fixed", "mob": "brute",
         "choice": "JUDGMENT: STR 14 = 10 + 2*(12//5), only the two completed floor sets' guaranteed potions by depth 12 (conservative). "
                   "Tier 4-5 weapons are therefore under-strength (accuracy/speed penalty) - intended."},
        {"id": "A_atReq", "label_ko": "중반 대조군: 영웅 Lv10, 무기 +0, 힘 = 무기 요구힘, 12층 브루트", "heroLevel": 10, "weaponLevel": 0,
         "heroStr": None, "strMode": "atReq", "mob": "brute",
         "choice": "Every weapon at exactly its STR requirement (no penalty, no bonus): isolates raw weapon stats."},
        {"id": "B", "label_ko": "후반: 영웅 Lv22, 무기 +6, 힘 18, 20층 골렘", "heroLevel": 22, "weaponLevel": 6, "heroStr": 18,
         "strMode": "fixed", "mob": "golem",
         "choice": "JUDGMENT: STR 18 = 10 + 2*(20//5), four completed floor sets by depth 20 (assumes every guaranteed potion was found). "
                   "The brief suggested ~16; change heroStr here and rerun."},
    ]
    out = []
    for sc in defs:
        mob = mobs[sc["mob"]]
        atk = 10 + (sc["heroLevel"] - 1)
        res = {w["id"]: dpt(w, sc["weaponLevel"], sc["heroStr"], atk, mob["defenseSkill"], mob["drMax"], sc["strMode"])
               for w in weapons}
        out.append({**sc, "attackSkill": atk, "results": res})
    return {"mobs": mobs, "inputSrc": src, "list": out,
            "limitations": ["Enchantments, glyphs, talents, rings, Duelist abilities, surprise attacks and Duelist charges are ignored.",
                            "Blocking weapons (shields, Quarterstaff, Katana, Rapier) are scored on offence only.",
                            "Single-target steady state; no enemy attacks, regeneration, or hero armor.",
                            "Mob defence/DR are base values; no Barkskin, champions, or ascension scaling.",
                            "Float32 rounding inside Random.NormalIntRange is ignored (pmf is exact for ideal floats)."]}


# ---------------------------------------------------------------- armor
def armors():
    out = []
    for cls, ko in (("ClothArmor", "clotharmor"), ("LeatherArmor", "leatherarmor"), ("MailArmor", "mailarmor"),
                    ("ScaleArmor", "scalearmor"), ("PlateArmor", "platearmor")):
        p = C / f"items/armor/{cls}.java"
        txt = p.read_text()
        tier = int(re.search(r"super\(\s*(\d+)\s*\)", txt).group(1))
        key = f"items.armor.{ko}"
        out.append({
            "id": cls, "src": rel(p), "tier": tier, "tierSrc": loc(p, r"super\(\s*\d+\s*\)"),
            "name": {"ko": msg(KOP, KO, key + ".name"), "en": msg(ENP, EN, key + ".name")},
            "desc": msg(KOP, KO, key + ".desc"),
            "dr": {"minBase": 0, "minPerLvl": 1, "maxBase": 2 * tier, "maxPerLvl": tier,
                   "formula": "DRMax = tier*(2+lvl); DRMin = lvl (while lvl < DRMax); hero drRoll = NormalIntRange(DRMin, DRMax)",
                   "maxSrc": loc(ARMOR_JAVA, r"int max = tier \* \(2 \+ lvl\)"),
                   "minSrc": loc(ARMOR_JAVA, r"public int DRMin\(int lvl\)"),
                   "rollSrc": loc(HERO_JAVA, r"belongings\.armor\(\)\.DRMin\(\)"),
                   "at0": [0, 2 * tier], "at6": [6, 8 * tier]},
            "strReq": {"base": 8 + 2 * tier, "byLevel": [str_req(tier, l) for l in range(0, 13)],
                       "src": loc(ARMOR_JAVA, r"protected static int STRReq\(int tier")},
            "sprite": sprite_rect(re.search(r"image = ItemSpriteSheet\.(\w+);", txt).group(1)),
        })
    rules = {
        "lowStr": [
            {"effect": "evasion divided by 1.5^(STRReq - STR)", "src": loc(ARMOR_JAVA, r"evasion /= Math\.pow\(1\.5, aEnc\)")},
            {"effect": "move speed divided by 1.2^(STRReq - STR)", "src": loc(ARMOR_JAVA, r"speed /= Math\.pow\(1\.2, aEnc\)")},
            {"effect": "armor DR roll reduced by 2*(STRReq - STR)", "src": loc(HERO_JAVA, r"armDr -= 2\*\(belongings\.armor\(\)\.STRReq\(\) - STR\(\)\)")},
        ],
        "excessStr": "No armor bonus from excess STR; it only avoids the penalties above.",
        "augment": [{"effect": "EVASION augment: evasion +round((2+lvl)*2), DR max +round((2+lvl)*-1); "
                               "DEFENSE augment: evasion round((2+lvl)*-2), DR max +round((2+lvl)*1)",
                     "src": loc(ARMOR_JAVA, r"EVASION \(2f")}],
    }
    cls_arm = C / "items/armor/ClassArmor.java"
    class_note = {
        "text": "Class armor defaults to tier 5 but copies the tier of the armor it was crafted from; same DR/STR formulas. "
                "Ability costs are not covered here.",
        "defaultTierSrc": loc(cls_arm, r"super\( 5 \)"),
        "inheritTierSrc": loc(cls_arm, r"classArmor\.tier = armor\.tier"),
    }
    return out, rules, class_note


# ---------------------------------------------------------------- enchantments / glyphs
PROC_NOTES = {
    "Kinetic": "No roll: always banks/adds ConservedDamage (overkill damage carries to the next hit).",
    "Projecting": "No roll: extends weapon reach, see Weapon.reachFactor.",
    "Crystal": "No roll: damage bonus with limited durability (see v4.0.1/v4.0.2 notes).",
    "Unstable": "Each hit procs a random other enchantment (Unstable.randomEnchants).",
    "Vampiric": "Heal chance depends on missing HP: 5% at full HP up to 30% at 0 HP (0.05 + 0.25*missingPercent).",
    "Grim": "maxChance is only reached at very low enemy HP (chance scales with enemy missing HP).",
    "Viscosity": "No roll: defers a share of damage via ViscosityTracker (level = armor lvl).",
    "Stone": "No proc roll: compares attacker accuracy and defender evasion (see source).",
}
NAME_ALIAS = {"AntiMagic": "antimagic"}


def parse_buckets(path, marker):
    txt = path.read_text()
    start_line = txt[:txt.index(marker)].count("\n") + 1
    block = txt[txt.index(marker):]
    res = {}
    for b in ("common", "uncommon", "rare"):
        m = re.search(rf"\b{b} = new Class<\?>\[\]\s*\{{(.*?)\}};", block, re.S)
        res[b] = re.findall(r"(\w+)\.class", m.group(1))
    tc = re.search(r"typeChances = new float\[\]\s*\{(.*?)\};", block, re.S).group(1)
    ch = [float(x) for x in re.findall(r"^\s*(\d+)", tc, re.M)]
    return res, ch, loc(path, r"\bcommon = new Class", start_line), loc(path, r"typeChances = new float", start_line)


def changelist_hits(names):
    """Lines of v4_X_Changes.java that name an enchant/glyph in bold or inside a button whose text discusses enchants/glyphs."""
    p = C / "ui/changelist/v4_X_Changes.java"
    lines = p.read_text().splitlines()
    sect, btn_of, starts, title = None, {}, {}, None
    cur_start = 0
    for i, l in enumerate(lines, 1):
        if m := re.search(r'new ChangeInfo\("([^"]+)"', l):
            sect = m.group(1)
        elif "new ChangeInfo(Messages.get" in l:
            sect = "v4.0"  # the flat new/changes/buffs/nerfs lists belong to the v4.0 header at the top of the file
        if "new ChangeButton(" in l:
            cur_start = i
            t = re.search(r'ChangeIcons\.\w+,\s*(?:"([^"]+)"|Messages\.get\(ChangesScene\.class, "(\w+)"\))', l)
            title = (t.group(1) or t.group(2)) if t else l.strip()
        btn_of[i] = (sect, title, cur_start)
    out = {n: [] for n in names}
    for i, l in enumerate(lines, 1):
        sec, bt, st = btn_of[i]
        text = re.sub(r'^\s*"|"\s*\+?\s*$', "", l).replace("\\n", "").strip()
        for n in names:
            if not re.search(rf"\b{n}\b", l, re.I):
                continue
            if re.search(rf"\*\*-?\s*{n}\*\*", l, re.I) or re.search("enchant|glyph", l + " " + (bt or ""), re.I):
                out[n].append({"version": sec, "section": bt, "quote": text, "src": f"{rel(p)}:{i}"})
    return out


def affixes(kind):
    if kind == "enchant":
        d, marker, owner = C / "items/weapon/enchantments", "public static abstract class Enchantment", WEAPON_JAVA
        key_pre = "items.weapon.enchantments."
    else:
        d, marker, owner = C / "items/armor/glyphs", "public static abstract class Glyph", ARMOR_JAVA
        key_pre = "items.armor.glyphs."
    mult = "procChanceMultiplier -> genericProcChanceMultiplier (ring of arcana, berserk etc.); 1.0 baseline, ignored here"
    buckets, tc, bsrc, tsrc = parse_buckets(owner, marker)
    total = sum(tc)
    rarity = {}
    for bi, b in enumerate(("common", "uncommon", "rare")):
        for cls in buckets[b]:
            rarity[cls] = {"bucket": b, "bucketChancePct": tc[bi] / total * 100,
                           "weightPct": round(tc[bi] / total * 100 / len(buckets[b]), 3)}
    out = []
    for p in sorted(d.glob("*.java")):
        cls = p.stem
        txt = p.read_text()
        key = key_pre + NAME_ALIAS.get(cls, cls.lower())
        pm = re.search(r"public int proc\(.*?\)\s*\{(.*?)\n\t\}", txt, re.S)
        proc_body = pm.group(1) if pm else ""
        em = re.search(r"float (procChance|healChance|maxChance)\s*=\s*([^;]+);", proc_body)
        entry = {"id": cls, "src": rel(p),
                 "name": {"ko": msg(KOP, KO, key + ".name"), "en": msg(ENP, EN, key + ".name")},
                 "desc": {"ko": msg(KOP, KO, key + ".desc")},
                 "curse": bool(re.search(r"boolean curse\(\)\s*\{\s*return true", txt)),
                 "rarity": rarity.get(cls)}
        if em:
            expr = " ".join(em.group(2).split())
            clean = re.sub(r"\s*\*\s*procChanceMultiplier\(\w+\)", "", expr).strip()
            try:
                vals = {lv: round(java_eval(clean, level=lv), 4) for lv in (0, 6)}
            except NameError:  # depends on runtime state (Vampiric: missing HP)
                vals = {0: None, 6: None}
            entry["proc"] = {"kind": em.group(1), "expr": expr, "exprWithoutMultiplier": clean,
                             "chanceAt0": vals[0], "chanceAt6": vals[6], "multiplier": mult,
                             "src": loc(p, rf"float {em.group(1)}\s*=")}
        else:
            c = re.search(r"//\s*(no proc effect[^\n]*)", proc_body)
            entry["proc"] = {"kind": "none", "expr": None, "chanceAt0": None, "chanceAt6": None,
                             "note": c.group(1) if c else None, "src": loc(p, r"public int proc")}
        if cls in PROC_NOTES:
            entry["proc"]["note"] = PROC_NOTES[cls]
        assert entry["name"]["ko"] and entry["desc"]["ko"], f"missing ko text for {cls}"
        assert entry["rarity"], f"{cls} missing from the common/uncommon/rare arrays"
        out.append(entry)
    pat = lambda e: "Anti-?Magic" if e["id"] == "AntiMagic" else e["id"]
    hits = changelist_hits([pat(e) for e in out])
    for e in out:
        e["changelog"] = hits[pat(e)]
    meta = {"buckets": buckets, "typeChances": tc, "bucketSrc": bsrc, "typeChancesSrc": tsrc,
            "note": "weightPct = typeChance / sum(typeChances) / bucket size, in percent"}
    return out, meta


# ---------------------------------------------------------------- main
weapons = melee_weapons()
armor_list, armor_rules, class_armor = armors()
sc = scenarios(weapons)
ench, ench_meta = affixes("enchant")
glyphs, glyph_meta = affixes("glyph")

W_ = {w["id"]: w for w in weapons}
A_ = {a["id"]: a for a in armor_list}
E_ = {e["id"]: e for e in ench}
G_ = {g["id"]: g for g in glyphs}

# ---------------------------------------------------------------- self-check (values hand-read from the .java files)
sw = W_["Sword"]  # Sword.java: tier 3, default min/max
assert sw["tier"] == 3 and sw["name"]["ko"]["text"] == "검"
assert (sw["damage"]["minBase"], sw["damage"]["maxBase"], sw["damage"]["maxPerLvl"]) == (3, 20, 4)
assert sw["strReq"]["base"] == 14 and sw["strReq"]["byLevel"][:4] == [14, 13, 13, 12]
assert not sw["damage"]["overridesMax"] and sw["ACC"]["value"] == 1.0 and sw["DLY"]["value"] == 1.0
fl = W_["Flail"]  # Math.round(7*(tier+1)) + lvl*Math.round(1.6f*(tier+1)), ACC 0.8
assert (fl["damage"]["maxBase"], fl["damage"]["maxPerLvl"], fl["ACC"]["value"]) == (35, 8, 0.8)
gl = W_["Glaive"]  # Math.round(6.67f*6)=40, lvl*Math.round(1.33f*6)=8, DLY 1.5, RCH 2
assert (gl["damage"]["maxBase"], gl["damage"]["maxPerLvl"], gl["RCH"]["value"], gl["DLY"]["value"]) == (40, 8, 2, 1.5)
ga = W_["Greataxe"]  # 5*(tier+4)=45; STRReq(tier+1)=20
assert (ga["damage"]["maxBase"], ga["strReq"]["base"]) == (45, 20)
gs = W_["Greatshield"]  # round(3*6)=18, lvl*(tier-1)=4*lvl; block 6+2*lvl
assert (gs["damage"]["maxBase"], gs["damage"]["maxPerLvl"]) == (18, 4)
assert (gs["defenseFactor"]["base"], gs["defenseFactor"]["perLvl"]) == (6, 2)
assert W_["Gauntlet"]["DLY"]["value"] == 0.5 and W_["Dagger"]["damage"]["maxBase"] == 8
pl = A_["PlateArmor"]  # tier 5: DR 0..10 at +0, 6..40 at +6; STR 18
assert pl["tier"] == 5 and pl["dr"]["at0"] == [0, 10] and pl["dr"]["at6"] == [6, 40] and pl["strReq"]["base"] == 18
assert A_["ClothArmor"]["dr"]["at0"] == [0, 2] and A_["ClothArmor"]["strReq"]["base"] == 10
assert abs(E_["Blazing"]["proc"]["chanceAt0"] - 1 / 3) < 1e-3 and abs(E_["Blazing"]["proc"]["chanceAt6"] - 7 / 9) < 1e-3
assert E_["Shocking"]["proc"]["chanceAt0"] == E_["Shocking"]["proc"]["chanceAt6"] == round(1 / 3, 4)
assert E_["Blazing"]["rarity"]["weightPct"] == 10.0 and E_["Corrupting"]["rarity"]["weightPct"] == 2.5
assert abs(G_["Thorns"]["proc"]["chanceAt0"] - 2 / 12) < 1e-3 and G_["Thorns"]["rarity"]["bucket"] == "rare"
assert not any(e["curse"] for e in ench + glyphs)
# DPT hand check: Sword +0 at its STR req vs brute: attackSkill 19, def 15 -> P(hit)=1-15/38, delay 1
r = sc["list"][1]["results"]["Sword"]
assert r["attackSkill"] == 19 and abs(r["pHit"] - (1 - 15 / 38)) < 1e-4 and r["delay"] == 1.0
assert abs(sum(k * p for k, p in normal_int_pmf(3, 20).items()) - 11.5) < 1e-9

gear = {
    "meta": {"game": "Shattered Pixel Dungeon",
             "version": re.search(r"appVersionName = '([^']+)'", (SRC / "build.gradle").read_text()).group(1),
             "honesty": "Every number is parsed from code (src), quoted from ko strings, or flagged JUDGMENT."},
    "sprites": SPRITES,
    "meleeWeapons": weapons,
    "scenarios": sc,
    "armor": {"items": armor_list, "rules": armor_rules, "classArmor": class_armor},
    "enchantments": {"items": ench, **ench_meta},
    "glyphs": {"items": glyphs, **glyph_meta},
}
OUT.mkdir(exist_ok=True)
(OUT / "gear.json").write_text(json.dumps(gear, indent=2, ensure_ascii=False) + "\n")
(OUT / "gear.js").write_text("// Generated by tools/extract_gear.py. Do not edit by hand.\n"
                             f"window.SPD_GEAR = {json.dumps(gear, ensure_ascii=False)};\n")

print(f"v{gear['meta']['version']}: {len(weapons)} melee, {len(armor_list)} armor, {len(ench)} enchants, {len(glyphs)} glyphs; "
      f"items.png {W}x{H} {SPRITES['bytes']}B")
for s in sc["list"]:
    rk = sorted(((v["dpt"], k) for k, v in s["results"].items()), reverse=True)
    print(s["id"], "TOP", [(k, d) for d, k in rk[:5]], "BOTTOM", [(k, d) for d, k in rk[-5:]])
