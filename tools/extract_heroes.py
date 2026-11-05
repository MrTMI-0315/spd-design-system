"""Extract hero classes, subclasses, armor abilities and talents from the Shattered Pixel Dungeon source tree.

Usage: python3 -I tools/extract_heroes.py <path-to-shattered-pixel-dungeon>
Writes data/heroes.json and data/heroes.js (window.SPD_HEROES) and copies talent_icons.png / hero_icons.png to assets/.
Every record carries "src": "path:line" relative to the SPD repo root. Korean text comes from *_ko.properties.
"""
import json, re, shutil, sys
from pathlib import Path

SRC = Path(sys.argv[1]).resolve()
OUT = Path(__file__).resolve().parent.parent
C = SRC / "core/src/main/java/com/shatteredpixel/shatteredpixeldungeon"
MSG = SRC / "core/src/main/assets/messages"
IFACE = SRC / "core/src/main/assets/interfaces"
CELL = 16


def rel(p):
    return str(p.relative_to(SRC))


def lines(path):
    return path.read_text().splitlines()


# ---------- properties ----------
def load_props(path):
    """key -> (value, 'path:line'); handles \\n, \\uXXXX and trailing-backslash continuations."""
    out, buf, start = {}, "", 0
    for i, line in enumerate(lines(path), 1):
        if not buf:
            if not line.strip() or line.lstrip().startswith(("#", "!")):
                continue
            start = i
        buf += line.lstrip() if buf else line
        if re.search(r"(?<!\\)(\\\\)*\\$", buf):
            buf = buf[:-1]
            continue
        k, _, v = buf.partition("=")
        v = re.sub(r"\\(u[0-9a-fA-F]{4}|.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), chr(int(m.group(1)[1:], 16)) if len(m.group(1)) == 5 else m.group(1)), v)
        out[k.strip()] = (v, f"{rel(path)}:{start}")
        buf = ""
    return out


ACT = load_props(MSG / "actors/actors_ko.properties")
ITM = load_props(MSG / "items/items_ko.properties")


def msg(props, key):
    if key not in props:
        raise KeyError(key)
    return props[key]


def key_of(path, suffix=""):
    """Messages key prefix for a Java file: package path below C, lowercased, dot separated."""
    return ".".join(p.lower() for p in path.relative_to(C).with_suffix("").parts) + suffix


# ---------- icons ----------
def rect(idx, sheet_w):
    cols = sheet_w // CELL
    return [idx % cols * CELL, idx // cols * CELL, CELL, CELL]


def hero_icon_consts():
    return {m.group(1): int(m.group(2)) for l in lines(C / "ui/HeroIcon.java")
            if (m := re.search(r"static final int (\w+)\s*=\s*(\d+);", l))}


HI = hero_icon_consts()
TALENT_W, HERO_W = 512, 128

# ---------- Talent.java ----------
TJ = C / "actors/hero/Talent.java"
TL = lines(TJ)


def parse_enum():
    out, started = {}, False
    for i, l in enumerate(TL, 1):
        if "public enum Talent" in l:
            started = True
            continue
        if not started:
            continue
        for m in re.finditer(r"\b([A-Z][A-Z_]+)\((\d+)(?:,\s*(\d+))?\)", l.split("//")[0]):
            out[m.group(1)] = {"icon": int(m.group(2)), "maxPoints": int(m.group(3) or 2), "line": i}
        if "RATFORCEMENTS" in l:
            break
    return out


ENUM = parse_enum()
# default maxPoints comes from Talent(int icon) -> this(icon, 2)
assert re.search(r"this\(icon,\s*2\)", "\n".join(TL))


def parse_lists(fn_pattern, tier_comment, case_re):
    """Walk a function; return {(case, tier): [(talent, line)]}. tier from '//tier N' comments, else None."""
    start = next(i for i, l in enumerate(TL) if re.search(fn_pattern, l))
    out, tier, cases = {}, None, []
    for i in range(start + 1, len(TL)):
        l = TL[i]
        if i > start + 2 and re.match(r"\tpublic static", l):
            break
        if tier_comment and (m := re.search(r"//tier\s?(\d)", l)):
            tier = int(m.group(1))
        if m := re.match(r"\s*((?:case \w+:\s*)+(?:default:)?|default:)\s*$", l):
            cases = re.findall(r"case (\w+):", m.group(1)) or ["DEFAULT"]
        if m := re.search(r"Collections\.addAll\(tierTalents,([^)]*)\)", l):
            for c in cases:
                out.setdefault((c, tier), []).extend((t.strip(), i + 1) for t in m.group(1).split(","))
    return out


CLASS_T = parse_lists(r"public static void initClassTalents\( HeroClass cls, ArrayList<LinkedHashMap<Talent, Integer>> talents, LinkedHashMap", True, None)
SUB_T = parse_lists(r"public static void initSubclassTalents\( HeroSubClass cls", False, None)

# ---------- HeroClass.java ----------
HC = C / "actors/hero/HeroClass.java"
HL = lines(HC)
CLASSES = re.findall(r"^\t(\w+)\( HeroSubClass\.(\w+), HeroSubClass\.(\w+) \)", "\n".join(HL), re.M)
assert [c[0] for c in CLASSES] == ["WARRIOR", "MAGE", "ROGUE", "HUNTRESS", "DUELIST", "CLERIC"]
SUBCLASS_SRC = next(i for i, l in enumerate(HL, 1) if "WARRIOR( HeroSubClass" in l)


def armor_abilities():
    """class -> [(AbilityClass, line)] from HeroClass.armorAbilities()."""
    start = next(i for i, l in enumerate(HL) if "public ArmorAbility[] armorAbilities" in l)
    out, cases = {}, []
    for i in range(start, start + 20):
        l = HL[i]
        if m := re.match(r"\s*case (\w+):", l):
            cases = [m.group(1)]
            if "default" in l:
                cases = [m.group(1)]
        if m := re.search(r"new ArmorAbility\[\]\{(.*)\}", l):
            out[cases[0]] = [(a, i + 1) for a in re.findall(r"new (\w+)\(\)", m.group(1))]
    return out


ABIL = armor_abilities()
assert all(len(v) == 3 for v in ABIL.values()) and len(ABIL) == 6


def find_java(name, root):
    hits = list(root.rglob(f"{name}.java"))
    assert len(hits) == 1, (name, hits)
    return hits[0]


# ---------- build talents ----------
TALENTS = {}


def talent(tid, tier, owner):
    if tid in TALENTS:
        return
    e = ENUM[tid]
    k = "actors.hero.talent." + tid.lower()
    title, tsrc = msg(ACT, k + ".title")
    desc, dsrc = msg(ACT, k + ".desc")
    rec = {"id": tid, "title_ko": title, "desc_ko": desc, "tier": tier, "owner": owner,
           "maxPoints": e["maxPoints"], "icon": e["icon"], "rect": rect(e["icon"], TALENT_W),
           "src": f"{rel(TJ)}:{e['line']}", "textSrc": {"title": tsrc, "desc": dsrc}}
    if k + ".meta_desc" in ACT:
        rec["metaDesc_ko"], rec["textSrc"]["metaDesc"] = ACT[k + ".meta_desc"]
    TALENTS[tid] = rec


def talent_refs(lst, tier, owner):
    ids = []
    for tid, ln in lst:
        talent(tid, tier, owner)
        ids.append(tid)
    return ids


# ---------- start items ----------
def item_info(cls):
    p = find_java(cls, C / "items")
    name, nsrc = msg(ITM, key_of(p, ".name"))
    return p, name, nsrc


def parse_items(start, end):
    """Parse `new X(` occurrences in HL[start:end] (0-based) into [{class, role, quantity, src}]."""
    body = HL[start:end]
    out = []
    for off, l in enumerate(body):
        for m in re.finditer(r"new (\w+)\(", l):
            cls = m.group(1)
            if cls in ("BrokenSeal",) or cls not in ALL_ITEM_CLASSES:
                if cls != "BrokenSeal":
                    continue
            var = (re.search(r"(\w+)\s*=\s*(?:\([^)]*\)\s*)?new " + cls, l) or [None, None])[1]
            rest_l = [l]
            for nl in body[off + 1:]:
                if var and re.search(r"\b" + var + r"\s*=[^=]", nl):
                    break  # var reassigned to another item
                rest_l.append(nl)
            rest = "\n".join(rest_l)
            role = None
            slot = re.search(r"belongings\.(weapon|armor|artifact)\s*=\s*\(?(?:\(" + cls + r"\)\s*)?(?:new " + cls + (r"|" + var if var else "") + r")\b", rest)
            if "new MagesStaff(new " + cls in l:
                role = "embedded"  # wand fused into the staff
            elif slot:
                role = slot.group(1)
            elif cls == "BrokenSeal":
                role = "seal"
            elif "collect()" in l or (var and re.search(r"\b" + var + r"\b[^;\n]*collect\(\)", rest)):
                role = "pack"
            elif re.match(r"\s*new " + cls + r"\(\)\.identify\(\)", l):
                role = "known_type"  # only marks the potion/scroll type as identified; no item is given
            if role is None:
                continue
            qty = 1
            p = find_java(cls, C / "items")
            if re.search(r"class " + cls + r"\s+extends MissileWeapon", p.read_text()):
                qty = 3  # MissileWeapon.defaultQuantity() -> 3 (MissileWeapon.java:357)
            if var and (q := re.search(r"\b" + var + r"\.quantity\((\d+)\)", rest)):
                qty = int(q.group(1))
            _, name, nsrc = item_info(cls)
            out.append({"class": cls, "name_ko": name, "role": role, "quantity": qty,
                        "src": f"{rel(HC)}:{start + off + 1}", "textSrc": nsrc})
    return out


ALL_ITEM_CLASSES = {p.stem for p in (C / "items").rglob("*.java")}


def func_range(sig):
    s = next(i for i, l in enumerate(HL) if sig in l)
    e = next(i for i in range(s + 1, len(HL)) if HL[i].startswith("\t}"))
    return s + 1, e


def start_items(cls):
    name = cls.capitalize()
    common = parse_items(*func_range("public void initHero"))
    # initHero's common part ends at the per-class switch; per-class items are only counted in initX
    common = [i for i in common if i["role"] != "seal"]
    own = parse_items(*func_range(f"private static void init{name}("))
    return common, own


# ---------- assemble ----------
classes, subclasses, abilities = [], [], []
tier_lists = {}
for cid, s1, s2 in CLASSES:
    ck = "actors.hero.heroclass." + cid.lower()
    keyc = "DEFAULT" if cid == "WARRIOR" else cid  # warrior is `case WARRIOR: default:`
    tl = {}
    for t in (1, 2, 3):
        lst = CLASS_T.get((cid, t)) or CLASS_T[("DEFAULT", t)] if cid == "WARRIOR" else CLASS_T[(cid, t)]
        tl[f"t{t}"] = talent_refs(lst, t, {"kind": "class", "id": cid})
        tl[f"t{t}Src"] = f"{rel(TJ)}:{lst[0][1]}"
    name, nsrc = msg(ACT, ck)
    short, ssrc = msg(ACT, ck + "_desc_short")
    full, fsrc = msg(ACT, ck + "_desc")
    unlock, usrc = msg(ACT, ck + "_unlock")
    common, own = start_items(cid)
    classes.append({
        "id": cid, "name_ko": name, "descShort_ko": short, "desc_ko": full, "unlock_ko": unlock,
        "startItemsCommon": common, "startItems": own, "talents": tl,
        "subclasses": [s1, s2], "armorAbilities": [a for a, _ in ABIL[cid]],
        "src": f"{rel(HC)}:{SUBCLASS_SRC + [c[0] for c in CLASSES].index(cid)}",
        "unlockSrc": f"{rel(HC)}:{next(i for i, l in enumerate(HL, 1) if 'public boolean isUnlocked' in l)}",
        "textSrc": {"name": nsrc, "descShort": ssrc, "desc": fsrc, "unlock": usrc}})

    for sc in (s1, s2):
        sk = "actors.hero.herosubclass." + sc.lower()
        sname, sns = msg(ACT, sk)
        sshort, sss = msg(ACT, sk + "_short_desc")
        sdesc, sds = msg(ACT, sk + "_desc")
        isrc = next(i for i, l in enumerate(lines(C / "actors/hero/HeroSubClass.java"), 1) if re.match(rf"\s*{sc}\(HeroIcon", l))
        idx = HI[sc]
        lst = SUB_T[(sc, None)] if (sc, None) in SUB_T else SUB_T[("DEFAULT", None)]
        subclasses.append({
            "id": sc, "class": cid, "name_ko": sname, "descShort_ko": sshort, "desc_ko": sdesc,
            "icon": idx, "rect": rect(idx, HERO_W), "src": f"{rel(C / 'actors/hero/HeroSubClass.java')}:{isrc}",
            "talents": talent_refs(lst, 3, {"kind": "subclass", "id": sc}),
            "talentsSrc": f"{rel(TJ)}:{lst[0][1]}",
            "textSrc": {"name": sns, "descShort": sss, "desc": sds}})

# armor abilities (+ Ratmogrify, which is not in HeroClass.armorAbilities())
ability_classes = {}
for cid, lst in ABIL.items():
    for a, ln in lst:
        ability_classes.setdefault(a, []).append(cid)


def ability(aname, cids, offered):
    p = find_java(aname, C / "actors/hero/abilities")
    txt = p.read_text()
    L = txt.splitlines()
    k = key_of(p)
    name, nsrc = msg(ACT, k + ".name")
    short, ssrc = msg(ACT, k + ".short_desc")
    desc, dsrc = msg(ACT, k + ".desc")
    extra = k + ".generic_desc"
    if extra in ACT:  # ElementalBlast / ElementalStrike append generic_desc outside GameScene
        desc += "\n\n" + ACT[extra][0]
    base = float(re.search(r"baseChargeUse\s*=\s*(\d+)", txt).group(1)) if "baseChargeUse" in txt else 35.0
    base_src = next((i for i, l in enumerate(L, 1) if "baseChargeUse =" in l), None)
    ck = k + ".cost" if k + ".cost" in ACT else "actors.hero.abilities.armorability.cost"
    cost = ACT[ck][0].replace("%d", str(int(base)))
    icon_line, icon_name = next((i, m.group(1)) for i, l in enumerate(L, 1) if (m := re.search(r"return HeroIcon\.(\w+);", l)))
    ids = [t for t in re.findall(r"Talent\.([A-Z_]+)", re.search(r"Talent\[\]\s*talents\(\).*?\{(.*?)\}", txt, re.S).group(1))]
    tline = next(i for i, l in enumerate(L, 1) if "new Talent[]" in l)
    tids = []
    for t in ids:
        if t == "HEROIC_ENERGY":
            continue
        talent(t, 4, {"kind": "ability", "id": aname.upper()})
        tids.append(t)
    # shared universal talent
    tids.append("HEROIC_ENERGY")
    idx = HI[icon_name]
    return {"id": aname.upper(), "class_name": aname, "name_ko": name, "descShort_ko": short, "desc_ko": desc,
            "cost_ko": cost, "chargeUse": base, "chargeSrc": f"{rel(p)}:{base_src}" if base_src else f"{rel(C / 'actors/hero/abilities/ArmorAbility.java')}:{next(i for i, l in enumerate(lines(C / 'actors/hero/abilities/ArmorAbility.java'), 1) if 'baseChargeUse' in l)}",
            "icon": idx, "rect": rect(idx, HERO_W), "iconSrc": f"{rel(p)}:{icon_line}",
            "classes": cids, "offered": offered, "talents": tids, "talentsSrc": f"{rel(p)}:{tline}",
            "src": rel(p), "textSrc": {"name": nsrc, "descShort": ssrc, "desc": dsrc}}


KC = f"{rel(C / 'actors/hero/HeroClass.java')}:" + str(next(i for i, l in enumerate(HL, 1) if "public ArmorAbility[] armorAbilities" in l))
for a, cids in ability_classes.items():
    abilities.append(ability(a, cids, {"how": "king_crown", "generallyAvailable": True, "src": KC}))

RK = C / "actors/mobs/npcs/RatKing.java"
rk_line = next(i for i, l in enumerate(lines(RK), 1) if "new Ratmogrify()" in l)
abilities.append(ability("Ratmogrify", [c[0] for c in CLASSES], {
    "how": "rat_king_with_crown", "generallyAvailable": False,
    "note": "HeroClass.armorAbilities() does not list it; only offered by the Rat King NPC (depth 5 Rat King room, or a distortion-trap summon) when the hero carries the King's Crown and wears armor.",
    "src": f"{rel(RK)}:{rk_line}",
    "roomSrc": f"{rel(C / 'levels/SewerBossLevel.java')}:{next(i for i, l in enumerate(lines(C / 'levels/SewerBossLevel.java'), 1) if 'RatKingRoom()' in l)}"}))

# HEROIC_ENERGY: shared T4 talent, icon depends on class (Talent.icon()), rat variant 218
talent("HEROIC_ENERGY", 4, {"kind": "shared", "id": "ABILITY"})
icon_src = next(i for i, l in enumerate(TL, 1) if "public int icon(){" in l)
he_icons = {}
for m in re.finditer(r"case (\w+):(?: default:)?\s*return (\d+);", "\n".join(TL[icon_src:icon_src + 30]).replace("\n", " ")):
    he_icons[m.group(1)] = int(m.group(2))
he_icons["RAT"] = int(re.search(r"useRatroicEnergy\)\{\s*return (\d+);", "\n".join(TL[icon_src:icon_src + 6])).group(1))
assert set(he_icons) == {c[0] for c in CLASSES} | {"RAT"}, he_icons
TALENTS["HEROIC_ENERGY"].update({
    "iconByClass": {k: {"icon": v, "rect": rect(v, TALENT_W)} for k, v in he_icons.items()},
    "iconSrc": f"{rel(TJ)}:{icon_src}"})
rt, rts = msg(ACT, "actors.hero.talent.heroic_energy.rat_title")
TALENTS["HEROIC_ENERGY"]["ratTitle_ko"], TALENTS["HEROIC_ENERGY"]["textSrc"]["ratTitle"] = rt, rts

# ---------- point budget ----------
thr_line = next(i for i, l in enumerate(TL, 1) if "tierLevelThresholds = new int" in l)
THR = [int(x) for x in re.search(r"new int\[\]\{([^}]*)\}", TL[thr_line - 1]).group(1).split(",")]
HERO = C / "actors/hero/Hero.java"
HRL = lines(HERO)
hl = lambda pat: next(i for i, l in enumerate(HRL, 1) if pat in l)
max_level = int(re.search(r"MAX_LEVEL = (\d+)", "\n".join(HRL)).group(1))
pdi = C / "items/potions/exotic/PotionOfDivineInspiration.java"
som = C / "items/scrolls/exotic/ScrollOfMetamorphosis.java"
tm, kc = C / "items/TengusMask.java", C / "items/KingsCrown.java"
f = lambda p, pat: f"{rel(p)}:{next(i for i, l in enumerate(lines(p), 1) if pat in l)}"
budget = {
    "tierLevelThresholds": THR, "tierLevelThresholdsSrc": f"{rel(TJ)}:{thr_line}",
    "maxLevel": max_level, "maxLevelSrc": f"{rel(HERO)}:{hl('MAX_LEVEL =')}",
    "tiers": [{"tier": t, "firstPointLevel": THR[t], "lastPointLevel": THR[t + 1] - 1, "points": THR[t + 1] - THR[t]} for t in range(1, 5)],
    "rule": "One point per hero level inside the tier's range (tier t: levels thresholds[t]..thresholds[t+1]-1). Unspent points are kept.",
    "ruleSrc": f"{rel(HERO)}:{hl('public int talentPointsAvailable')}",
    "locks": {"tier3": "no points until a subclass is chosen (subClass == NONE)",
              "tier4": "no points until an armor ability is chosen (armorAbility == null)",
              "src": f"{rel(HERO)}:{hl('public int talentPointsAvailable') + 1}"},
    "subclass": {"item": "TengusMask", "name_ko": msg(ITM, "items.tengusmask.name")[0],
                 "how": "dropped by Tengu on death if the hero has no subclass yet; wearing it opens the subclass choice. No level check on wearing.",
                 "src": [f(C / "actors/mobs/Tengu.java", "new TengusMask()"), f(tm, "WndChooseSubclass"), f(C / "windows/WndChooseSubclass.java", "tome.choose")],
                 "textSrc": msg(ITM, "items.tengusmask.name")[1]},
    "armorAbility": {"item": "KingsCrown", "name_ko": msg(ITM, "items.kingscrown.name")[0],
                     "how": "dropped by the Dwarf King on death; wearing it with armor equipped opens the ability choice and upgrades the armor into class armor. Ratmogrify instead via the Rat King NPC.",
                     "src": [f(C / "actors/mobs/DwarfKing.java", "new KingsCrown()"), f(kc, "WndChooseAbility"), f(kc, "Talent.initArmorTalents")],
                     "textSrc": msg(ITM, "items.kingscrown.name")[1]},
    "extraPoints": [{
        "item": "PotionOfDivineInspiration", "name_ko": msg(ITM, "items.potions.exotic.potionofdivineinspiration.name")[0],
        "desc_ko": msg(ITM, "items.potions.exotic.potionofdivineinspiration.desc")[0],
        "effect": "+2 talent points in one chosen tier (1-4); usable once per tier, so at most +8 in total; the tier must be open (subclass/ability chosen for tiers 3/4) to spend them.",
        "src": [f"{rel(HERO)}:{hl('public int bonusTalentPoints')}", f(pdi, "enabled[1] = enabled[2]"), f(pdi, "boostedTiers = new boolean")],
        "textSrc": msg(ITM, "items.potions.exotic.potionofdivineinspiration.desc")[1]}],
    "noExtraPoints": [{
        "item": "ScrollOfMetamorphosis", "name_ko": msg(ITM, "items.scrolls.exotic.scrollofmetamorphosis.name")[0],
        "desc_ko": msg(ITM, "items.scrolls.exotic.scrollofmetamorphosis.desc")[0],
        "effect": "Adds no points. Swaps one tier 1-3 class talent for a random same-tier talent from each other class (options exclude talents you already have); points already put in carry over. Subclass and armor talents cannot be swapped.",
        "src": [f(som, "Talent.initClassTalents(Dungeon.hero.heroClass"), f(som, "for (HeroClass cls : HeroClass.values())"), f(som, "options.put(Random.element")],
        "textSrc": msg(ITM, "items.scrolls.exotic.scrollofmetamorphosis.desc")[1]}],
}

# ---------- write ----------
version = re.search(r"appVersionName = '([^']+)'", (SRC / "build.gradle").read_text()).group(1)
data = {
    "meta": {"game": "Shattered Pixel Dungeon", "version": version},
    "images": {"talentIcons": {"asset": "assets/talent_icons.png", "size": [512, 128], "cell": CELL},
               "heroIcons": {"asset": "assets/hero_icons.png", "size": [128, 256], "cell": CELL}},
    "classes": classes, "subclasses": subclasses, "abilities": abilities,
    "talents": TALENTS, "pointBudget": budget,
}

# ---------- self-check ----------
w = next(c for c in classes if c["id"] == "WARRIOR")
assert w["talents"]["t1"] == ["HEARTY_MEAL", "VETERANS_INTUITION", "PROVOKED_ANGER", "IRON_WILL"]
assert w["talents"]["t2"] == ["IRON_STOMACH", "LIQUID_WILLPOWER", "RUNIC_TRANSFERENCE", "LETHAL_MOMENTUM", "IMPROVISED_PROJECTILES"]
assert TALENTS["HEARTY_MEAL"]["maxPoints"] == 2 and TALENTS["HOLD_FAST"]["maxPoints"] == 3 and TALENTS["BODY_SLAM"]["maxPoints"] == 4
assert TALENTS["HOLD_FAST"]["rect"] == [144, 0, 16, 16] and TALENTS["EMPOWERING_MEAL"]["rect"] == [0, 16, 16, 16]
assert subclasses[0]["id"] == "BERSERKER" and subclasses[0]["rect"] == [0, 0, 16, 16]
assert budget["tiers"][0]["points"] == 5 and budget["tiers"][3]["points"] == 10 and THR == [0, 2, 7, 13, 21, 31]
assert [len(c["talents"][t]) for c in classes for t in ("t1", "t2", "t3")] == [4, 5, 2] * 6
assert all(len(s["talents"]) == 3 for s in subclasses) and len(subclasses) == 12
assert len(abilities) == 19 and all(len(a["talents"]) == 4 for a in abilities)
assert sorted(next(a for a in abilities if a["id"] == "RATMOGRIFY")["talents"]) == ["HEROIC_ENERGY", "RATFORCEMENTS", "RATLOMACY", "RATSISTANCE"]
assert len(TALENTS) == len(ENUM) - 0, (len(TALENTS), len(ENUM))  # every enum talent is reachable
sp = next(i for c in classes if c["id"] == "DUELIST" for i in c["startItems"] if i["class"] == "ThrowingSpike")
assert sp["quantity"] == 2

(OUT / "data").mkdir(exist_ok=True)
(OUT / "data/heroes.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
(OUT / "data/heroes.js").write_text(
    "// Generated by tools/extract_heroes.py. Do not edit by hand.\n"
    f"window.SPD_HEROES = {json.dumps(data, ensure_ascii=False)};\n")
for n in ("talent_icons.png", "hero_icons.png"):
    shutil.copyfile(IFACE / n, OUT / "assets" / n)

print(f"v{version}: " + ", ".join(
    f"{c['id']} t1/t2/t3={len(c['talents']['t1'])}/{len(c['talents']['t2'])}/{len(c['talents']['t3'])}" for c in classes)
    + f"; {len(subclasses)} subclasses, {len(abilities)} abilities, {len(TALENTS)} talents")
