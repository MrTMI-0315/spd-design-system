# Brief: SPD v4.0.2 class build drafts

You are drafting recommended builds for a Korean fan page about Shattered Pixel Dungeon **v4.0.2** (latest release, commit 57a4e06).
The user wants "최적 빌드" and insists on the latest version. v4.0 shipped after our knowledge cutoff and no v4.0.x community stats or
tier lists exist (checked 2026-11-05), so **do not lean on remembered meta**. Every claim must carry one provenance tag:

- `코드 계산` — a number computed from code (e.g. DPT from data/gear.json scenarios). Quote the number.
- `설명문 기준` — a number or effect from the in-game Korean description (data/heroes.json `desc_ko`, gear.json texts). Quote the number.
- `추정` — your judgment. Allowed, but say why in one clause. Prefer reasoning from numbers over vibes.

If a talent description is ambiguous, read the Java code in the SPD repo and cite it (`path:line`, relative to the SPD repo root).

## Inputs (read-only)
- `data/heroes.json` — classes, subclasses, armor abilities, all 160 talents (Korean title/desc, tier, maxPoints, owner).
- `data/gear.json` — 32 melee weapons with DPT in scenarios `A` (Lv10, STR 14, +0 vs 12층 Brute), `A_atReq` (STR = weapon req), `B` (Lv22, STR 18, +6 vs 20층 Golem); armor; 17 enchantments, 13 glyphs (proc formulas, Korean text, v4.0 change notes). Read `scenarios.limitations` before using DPT.
- SPD source: `/Users/mrtmi/Desktop/Mr_TMI/vibe-projects/spd-analysis/shattered-pixel-dungeon`
  (Java under `core/src/main/java/com/shatteredpixel/shatteredpixeldungeon/`).
- Site dir (cwd): `/Users/mrtmi/Desktop/Mr_TMI/vibe-projects/spd-analysis/spd-design-system`

## Point budget (verified from code)
- Tier points: T1 = 5 (Lv2–6), T2 = 6 (Lv7–12), T3 = 8 (Lv13–20, shared between the class's 2 T3 talents and the subclass's 3), T4 = 10 (Lv21–30, the chosen armor ability's 3 talents + HEROIC_ENERGY).
- Each talent ≤ its `maxPoints`. Spend exactly the budget in each tier.
- Potion of Divine Inspiration (신성한 영감의 물약): +2 points to one tier, once per tier. Put these in the optional `bonus` list (≤ 2 per tier), not in the main allocation.
- Subclass is chosen via 텐구의 가면 (after Tengu, depth 10); armor ability via 드워프 제왕의 왕관 (after Dwarf King, depth 20).

## Output
Write one file per class: `data/builds/<CLASS_ID>.json` (CLASS_ID as in heroes.json, e.g. `WARRIOR`). UTF-8, Korean prose, English ids. Schema:

```json
{
  "class": "WARRIOR",
  "summary": "직업 운영 한두 문장",
  "summaryTag": "추정",
  "subclassVerdict": { "pick": "BERSERKER", "why": "…", "tag": "추정" },
  "builds": [
    {
      "subclass": "BERSERKER",
      "title": "짧은 빌드 이름",
      "concept": "한두 문장",
      "talents": [
        { "id": "HEARTY_MEAL", "points": 1, "why": "…", "tag": "설명문 기준", "quote": "+1: 체력 33% 이하에서 4 회복" }
      ],
      "bonus": [ { "tier": 3, "id": "…", "points": 2, "why": "…", "tag": "추정" } ],
      "armorAbility": { "id": "HEROICLEAP", "why": "…", "tag": "추정" },
      "gear": [
        { "slot": "weapon", "ref": "Greataxe", "why": "B 시나리오 DPT 30.7로 1위", "tag": "코드 계산" },
        { "slot": "glyph", "ref": "<glyph id from gear.json>", "why": "…", "tag": "설명문 기준" },
        { "slot": "ring|wand|artifact|other", "name": "한국어 아이템명", "why": "…", "tag": "추정" }
      ],
      "playstyle": "2~3문장: 초반/중반/후반 운영",
      "playstyleTag": "추정"
    }
  ]
}
```

Rules:
- `builds` has exactly one build per subclass (2 builds), and `talents` covers T1, T2, T3 (class + that subclass) and T4 (the chosen ability) with the exact budgets above. T1/T2 may be identical between the two builds if that is the honest answer.
- `gear.ref` must be an `id` that exists in gear.json (meleeWeapons / armor / enchantments / glyphs); use `name` only for slots gear.json does not cover (rings, wands, artifacts, missiles…). Weapon picks should cite DPT from the relevant scenario, and STR requirement trade-offs (scenario A punishes tier 4–5 weapons at STR 14).
- `why` ≤ 70 Korean characters. `quote` is required when tag is 설명문 기준 or 코드 계산.
- Do not invent statistics, win rates or community opinions.
- Validate your own JSON: budgets per tier, maxPoints, talent ownership (class/subclass/ability must match). A quick Python check is fine; delete any scratch scripts afterwards.

Report back in under 25 lines: files written, one line per build (title + key idea), and anything you were unsure about.
