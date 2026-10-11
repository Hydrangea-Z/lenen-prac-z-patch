# Len'en Practice Tools · Hint Manual

Applies to **Reactivate majestical imperial (Le03) v0.5.9** and **Earthen Miraculous Sword (Le02) v0.7.8**.

Both games use the same hint system and the same file format. A few details differ;
where they do, both values are given. This file is `.md`, so **the game never reads it** —
it is safe to keep inside the `hint\` folder.

> Chinese edition: `使用说明.md` / `使用说明.html` (section-for-section equivalent).

---

## 0. In one sentence

Drop `.txt` files into the game's `hint\` folder and the game picks them up.
Each line describes one thing: **when to show it, where on the playfield, and what to draw.**

```
+  16  all  1200  192,348  1800
│  │   │    │     │        └─ when it stops showing
│  │   │    │     └────────── where (x,y)
│  │   │    └──────────────── when it starts showing
│  │   └───────────────────── which character it applies to
│  └───────────────────────── marker size
└──────────────────────────── marker shape
```

---

## 1. Where the files go

```
<game folder>\
  Le03prac.exe   (or Le02prac.exe)
  hint\            ← put them here
    1.txt
    3-easy.txt
    all.txt
```

- The folder must be named `hint` and sit **next to the exe**.
- Only **`.txt`** is read; `.md`, `.bak`, `.userbak-*` and friends are ignored.
- Files are read **once when a stage starts**. After editing, **re-enter the stage**
  to see the change — no need to restart the game.
- Switching stages re-reads them, so leaving a stage and coming back also refreshes.

---

## 2. File names and difficulty

File names are free-form, but each file must say **which stage it belongs to**:

```
3              ← a bare number on its own line means stage 3
```
or
```
stage 3
```

Either layout works, and you can mix them:

- **One file per stage**: `1.txt`, `2.txt`, `7.txt`, …
- **Everything in one file**: `all.txt`, switching stages with `stage N`

**Difficulty filter** (in the file name, case-insensitive):

| File name contains | Loads only on |
|---|---|
| `-easy` | Easy |
| `-normal` | Normal |
| `-hard` | Hard |
| `-unreal` | Unreal |
| none of the above | every difficulty |

> ⚠️ **The Extra difficulties have no tag of their own.**
> The game has seven difficulties —
> `Easy / Normal / Hard / Unreal / EasyExtra / Extra / AbsurdlyExtra` —
> but only the first four have tags. **Any difficulty index above Unreal is treated as Easy**, so:
> `3-easy.txt` **also loads** on EasyExtra / Extra / AbsurdlyExtra, while
> `-normal`, `-hard` and `-unreal` **do not load** on the Extra difficulties.

---

## 3. Line format

```
<marker>  <size>  <character>  <start>  <position>  <end>
```

- Fields may be separated by **spaces, tabs or commas** — mixing is fine.
- `#` to end of line is a comment; blank lines are ignored.
- **Unrecognised lines are skipped silently. Nothing ever errors out.**

### Marker (field 1)

| Symbol | What is drawn |
|---|---|
| `+` | **Crosshair** — its centre is the point |
| `-` | **Horizontal dashed line** (horizontal safe line), spanning the full playfield width |
| `\|` | **Vertical dashed line** (vertical safe line), spanning the full playfield height |
| anything else | treated as `+` |

`-` only uses the **y** of the position (the x is ignored);
`|` only uses the **x** (the y is ignored).
The capture tool always writes a point — just change the symbol to turn it into a safe line.

### Size (field 2)

Marker size, default `16`.

- `+`: roughly the diameter of the judgement point works well. `16` draws about 50 px wide.
- `-` / `|`: **the length of each dash** (the gap equals the dash, so it alternates dash/blank).

### Character (field 3)

- `all` — show for every character (this is what the capture tool writes)
- `1` `2` `3` `4` — show only for the Nth character, in the game's own order
- **Anything else, including character names, is treated as `all`** —
  when in doubt it shows too much rather than hiding something by mistake.

### Position (field 5)

`x,y` in playfield coordinates:

- **x: `0 .. 384`**
- **y: `0 .. 448`, increasing downwards**

This is exactly the value the F12 `Capture` row writes.
A bad position is **not** rejected — it is simply drawn off-screen.

---

## 4. Start / end (fields 4 and 6)

Two notations. **Both ends of a line must use the same one**;
a line that mixes them (one end absolute, one end boss) is **skipped**.

### (a) Absolute stage frame — for mid-stage

Just write the frame number, e.g. `1200`. Read the current frame from the F12 `Frame:` row.
**60 frames = 1 second.**

### (b) `boss:<pattern>:<frame>` — for boss fights

For example `boss:2:60`.

- **`<pattern>` is 0-based**, and it is exactly the number the F12 `Pattern:` row shows.
  Press F12 and look at that row before writing one, and you cannot get it wrong.
- `<frame>` counts from the start of that pattern; 60 frames = 1 second.

### ★ The time window is half-open

The window covers `start <= now < end` — **the end value itself is not included**.

- An end of `boss:4:0` means "it ends the moment pattern 4 begins",
  i.e. "until pattern 3 finishes" — it does **not** spill into pattern 4.
- Absolute frames work the same way: `120` to `900` covers frames 120..899.

The two ends may name **different patterns**, e.g. `boss:2:60` to `boss:4:0`
means "from frame 60 of pattern 2 until pattern 4 begins".

### ★ Mid-stage vs. boss

**Mid-stage (no boss on screen) the `Pattern:` row shows `-1`**, which is kept
strictly distinct from `0`. So a `boss:0:…` entry never lights up mid-stage,
and conversely absolute-frame entries keep working during a boss fight.

---

## 5. Marking things yourself (recommended workflow)

1. Enter a stage and press **F12**.
2. Make sure **`Hint:` is `on`** (it is by default).
3. Fly the player to the spot you want to mark.
4. Move the cursor to the **`Capture:`** row and press **Z**:
   - It appends **the current position and the current time** to the `.txt` for
     **the stage you are in** (stage 7 writes `7.txt`; a missing file is created
     automatically, with the stage number as its header).
   - **Mid-stage**: start = the current frame, end = the end of the current section.
   - **Boss fight**: it writes `boss:<current pattern>:<frames into it>` to
     `boss:<next pattern>:0` — i.e. "from now until this pattern ends".
     **You never have to count patterns yourself.**
   - A trailing newline is added, so repeated captures never glue together.
5. Open the txt and fine-tune it (change the marker, the size, the times), then save.
   **It takes effect the next time you enter the stage.**

The number to the right of `Capture:` is how many entries you have written this session.

---

## 6. F12 menu quick reference

Both games have **12 rows**, but the order differs slightly:

**Reactivate majestical imperial (Le03)**
```
No Gameover / Lock Power / Hint / Player + / Capture / Pattern /
Hit / Lock Seed / Seed / Frame / Fix X / Fix Y
```

**Earthen Miraculous Sword (Le02)**
```
No Gameover / Lock Power / Hint / Player + / Capture / Frame /
Pattern / Lock Seed / Seed / Hit / Fix X / Fix Y
```

| Key | Action |
|---|---|
| `↑` `↓` | move the cursor (wraps at both ends) |
| `←` `→` | change the value (hold for continuous fine steps) |
| `Z` | flip a switch row; `Capture` = capture once; `Seed` = start digit entry |
| while open | the game itself receives no input |

What the rows mean:

- **`Hint:`** — master switch for hint markers, default `on`
- **`Player +:`** — the player's judgement-point crosshair, default `on`
- **`Capture:`** — press Z to write the current position + time into this stage's txt
- **`Pattern:`** — read-only. Current boss pattern number (**0-based**); `-1` mid-stage
- **`Frame:`** — read-only. Current stage frame
- **`Hit:`** — read-only. Times hit (**reset on every stage entry**, including retries)
- **`Fix X:` / `Fix Y:`** — calibration for the judgement-point crosshair (next section)
- **`Seed:` / `Lock Seed:`** — RNG seed locking

---

## 7. The `Player +` crosshair and `Fix X/Y`

- `Player +` draws **the player's judgement point**, using **the same coordinate
  transform as the hint markers**. So when you place a hint under your own feet,
  the two crosses **must coincide** — that is deliberate, and you can use it to check
  one against the other.
- If the crosshair is slightly off the little dot the game draws, fine-tune it with
  **`Fix X` / `Fix Y`**:
  - default `64` = no shift (Le02 ships at `65`, i.e. one step right)
  - **larger = further right / further down**
  - one step is roughly 0.8 px in Le03 and 0.6 px in Le02, so you can land it very precisely
- **The hint markers follow the same calibration**, so you only align it once.

---

## 8. The settings file `prac.cfg`

Next to the exe, plain text, one setting per line:

```
playerplus=1
```

- Only the **`Player +`** switch is remembered today.
- **No file = the built-in default (`on`)**. Any change you make in the menu is
  **written back immediately**.
- So: turn it off once and it stays off on the next launch. Delete `prac.cfg` to
  restore the default.
- A read-only game folder still plays fine — it just cannot remember the setting.

---

## 9. Differences between the two games

| | Le03 | Le02 |
|---|---|---|
| hint folder | `<game folder>\hint\` | same |
| Line format | identical | identical |
| Menu order | `Pattern` before `Hit` | `Frame` before `Pattern` |
| `Fix X` factory value | `64` | `65` |
| Crosshair size | about 25 px | about 27 px |
| Pattern table | Appendix B | Appendix A |

---

## 10. Troubleshooting

| Symptom | Check first |
|---|---|
| **Nothing shows at all** | is `Hint:` `on`; is the file name / stage header right; does `Frame` or `Pattern` fall inside the window |
| **Only some entries show** | window written backwards, or the two ends use different notations (absolute vs `boss:`) |
| **A boss hint shows early / late** | is the `P` in `boss:P:F` 0-based — press F12 and check the `Pattern:` row |
| **Difficulty filter seems ignored** | the Extra difficulties are treated as Easy (section 2) |
| **Position looks right but nothing is visible** | is x/y inside `0..384` / `0..448` |
| **Edited the file, nothing changed** | you must **re-enter the stage** to re-read the files |
| **`Capture` wrote the wrong spot** | make sure `Fix X/Y` is at 64 (or your calibrated value); the `Player +` cross sits on that point |

Other built-in tolerances:

- unrecognised lines → skipped, no error
- lines whose stage does not match → skipped (e.g. stage-2 content inside `1.txt`)
- hint lines before any stage number → skipped
- out-of-range positions → drawn anyway, just off-screen

---

## Appendix A: Le02 (Earthen Miraculous Sword) pattern numbers

The number is the **P** you write in `boss:P:F`.
`MNon` = midboss non-spell, `MSpell` = midboss spell, `Non` = boss non-spell,
`Spell` = boss spell card.
(The practice menu's first entry, `None`, means "no pattern" and has no valid P, so it is omitted.)

| Stage | pattern numbers |
|---|---|
| **1** | `0` MNon 1 / `1` MSpell 1 / `2` Non 1 / `3` Spell 1 / `4` Non 2 / `5` Spell 2 |
| **2** | `0` MSpell 1 / `1` Non 1 / `2` Spell 1 / `3` Non 2 / `4` Spell 2 / `5` Non 3 / `6` Spell 3 / `7` Spell 4 |
| **3** | `0` MNon 1 / `1` MSpell 1 / `2` Non 1 / `3` Spell 1 / `4` Non 2 / `5` Spell 2 / `6` Non 3 / `7` Spell 3 / `8` Spell 4 / `9` Spell 5 |
| **4** | `0` MNon 1 / `1` MSpell 1 / `2` Non 1 / `3` Spell 1 / `4` Non 2 / `5` Spell 2 / `6` Spell 3 / `7` Spell 4 |
| **5** | `0` MNon 1 / `1` MSpell 1 / `2` Non 1 / `3` Spell 1 / `4` Non 2 / `5` Spell 2 / `6` Non 3 / `7` Spell 3 / `8` Non 4 / `9` Spell 4 |
| **6** | `0` MNon 1 / `1` MSpell 1 / `2` Non 1 / `3` Spell 1 / `4` Non 2 / `5` Spell 2 / `6` Non 3 / `7` Spell 3 / `8` Non 4 / `9` Spell 4 / `10` Spell 5 / `11` Spell 6 / `12` Tasouken P1–P6 |
| **7** | `0` MSpell 1 / `1` MSpell 2 / `2` MSpell 3 / `3` Non 1 / `4` Spell 1 / `5` Non 2 / `6` Spell 2 / `7` Non 3 / `8` Spell 3 / `9` Non 4 / `10` Spell 4 / `11` Non 5 / `12` Spell 5 / `13` Non 6 / `14` Spell 6 / `15` Non 7 / `16` Spell 7 / `17` Non 8 / `18` Spell 8 / `19` Spell 9 / `20` Spell 10 |

> Stage 6's `Tasouken P1–P6` share one P (`12`): they are phases of a single pattern,
> so `boss:12:F` covers the whole thing.

---

## Appendix B: Le03 (Reactivate majestical imperial) pattern numbers

| Stage | pattern numbers |
|---|---|
| **1** | `0` MNon 1 / `1` MSpell 1 / `2` Non 1 / `3` Spell 1 / `4` Non 2 / `5` Spell 2 |
| **2** | `0` MNon 1 / `1` MSpell 1 / `2` Non 1 / `3` Spell 1 / `4` Non 2 / `5` Spell 2 / `6` Non 3 / `7` Spell 3 |
| **3** | `0` MNon 1 / `1` MSpell 1 / `2` Non 1 / `3` Spell 1 / `4` Non 2 / `5` Spell 2 / `6` Non 3 / `7` Spell 3 / `8` Spell 4 / `9` Spell 5 |
| **4** | `0` Non 1 / `1` Spell 1 / `2` Spell 2 / `3` Non 2 / `4` Spell 3 / `5` Spell 4 / `6` Non 3 / `7` Spell 5 |
| **5** | `0` MNon 1 / `1` MSpell 1 / `2` Non 1 / `3` Spell 1 / `4` Non 2 / `5` Spell 2 / `6` Non 3 / `7` Spell 3 / `8` Non 4 / `9` Spell 4 / `10` Spell 5 |
| **6** | `0` Non 1 / `1` Spell 1 / `2` Non 2 / `3` Spell 2 / `4` Non 3 / `5` Spell 3 / `6` Spell 4 / `7` Spell 5 |
| **7** | `0` MSpell 1 / `1` MSpell 2 / `2` MSpell 3 / `3` Non 1 / `4` Spell 1 / `5` Non 2 / `6` Spell 2 / `7` Non 3 / `8` Spell 3 / `9` Non 4 / `10` Spell 4 / `11` Non 5 / `12` Spell 5 / `13` Non 6 / `14` Spell 6 / `15` Non 7 / `16` Spell 7 / `17` Non 8 / `18` Spell 8 / `19` Spell 9 / `20` Spell 10 / `19` PMiBR P1–P5 |

> Stages 4 and 6 have no midboss, so the numbering starts at the boss.
> Stage 7's last five entries, `PMiBR P1–P5`, share P = `19`.

> **These tables are a convenience — the F12 `Pattern:` row is the ground truth.**
> Whatever that row shows is the number to write.

---

## Appendix C: Complete examples

`hint\1.txt`
```
# Stage 1
1

# marker size char  start       position    end
# Mid-stage: a crosshair on the usual route, frames 120 to 900
+       16   all   120         192,348     900

# Mid-stage: a horizontal safe line from frame 900 to the end of the section
-       24   all   900         192,348     1200

# Boss: the whole midboss non-spell, only for the 2nd character
+       16   2     boss:0:0    100,200     boss:1:0

# Boss: a vertical safe line from frame 60 of the mid spell until boss spell 1 starts
|       16   all   boss:1:60   64,200      boss:3:0

# Unrecognised lines are skipped -- e.g. this one, whose two ends disagree
+       16   all   120         192,348     boss:2:0
```

`hint\3-easy.txt` (Easy-family difficulties only)
```
3
+  16  all  boss:0:0  300,200  boss:1:0
```

`hint\all.txt` (single merged file)
```
stage 1
+  16  all  120  192,348  400

stage 2
+  16  all  250  100,200  600
```

---

## Appendix D: For people writing scripts

- Each `.txt` is parsed line by line. The stage number is taken from `stage N`
  or a bare number; every hint line after it belongs to that stage.
- Fields within a line are split on whitespace or commas; `boss:P:F` is split into
  three tokens.
- The `P` in `boss:P:F` is **the game's own 0-based number**. The practice tool does
  not add or subtract anything.
- Time windows compare as `[start, end)`; when the patterns are equal it compares the
  frame within the pattern.
- Position limits are x 384 / y 448. Going over is not an error — it just draws
  off-screen.
