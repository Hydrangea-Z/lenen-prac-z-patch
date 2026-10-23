# Len'en Practice Tools · Hint Manual

Applies to **无现里 / Lenen's *Brilliant Imperishable* (Le01) v0.2.0**,
**蛇丛剑 / *Earthen Miraculous Sword* (Le02) v0.8.0** and
**灵烈传 / *Reactivate majestical imperial* (Le03) v0.6.0**.

All three games use the same hint system and the same F12 menu (a main table plus a
10-row hint settings panel). A few details differ; where they do, both values are
given -- for instance **Le03 has two characters, so its main menu carries an extra
`Lock P2` row**. **The pause-menu hotkeys (`R` restart stage / `Q` back to title)
exist in all three games** — see section 6.5. This file is `.md`, so
**the game never reads it** — it is safe to keep inside the `hint\` folder.

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
<marker>  <size>  <character>  <start>  <position>  <end>  [R,G,B]
```

Those last three numbers are **optional** (see "Colour" below).

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

### Colour (fields 7-9, optional) — all three games, v0.1.9 / v0.7.13 / v0.5.15 and up

Add **three decimal numbers in 0..255** at the end of the line and that marker
gets its own colour:

```
+  16  all  120  192,348  400  255,80,0      <- orange
-  16  all  120  100,300  900  0,255,255     <- cyan
+  16  all  120  192,348  400                <- omitted = use the Hint col row
```

- The three numbers may be separated by **commas or spaces** (as with the
  position), so `255,80,0` and `255 80 0` are the same thing.
- **All three are required.** If only one or two are given, or the trailing
  fields are not numbers at all (a trailing comment, say), the line is treated
  as "no colour given" and **follows the F12 `Hint col` row**. Falling back to
  the default is deliberate: it never guesses.
- The colour applies to **every** marker shape (`+`, `-`, `|`).
- Markers dim when the player stands on them; the dim colour is computed as
  **each channel halved**, so it works for any colour you pick.
- **Existing files need no changes**: a six-column line keeps using
  `Hint col`, exactly as before.

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
4. Put the cursor on **`Hint:`** and press **Z** to open the **hint settings
   panel**, then move the cursor to the **`Capture:`** row and press **Z**:
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
**ESC** goes back to the main menu; **F12** closes the whole overlay.

---

## 6. F12 menu quick reference

### Main menu + hint settings panel

**Main menu (Le01 / Le02, 6 rows)**
```
No Gameover / Lock Power / Hint / Lock Seed / Seed / Hit
```

**Le03 has 7 rows** -- it is the one game with two characters, and each character
keeps its own power value, so `Lock Power` splits in two:
```
No Gameover / Lock P1 / Lock P2 / Hint / Lock Seed / Seed / Hit
```
`Lock P1` freezes the main character's power and `Lock P2` the partner's;
**the two switches are independent** (you can lock just one).

**Hint settings panel (10 rows)** — put the cursor on the `Hint` row and press
**Z**; the title becomes `F12 - HINT (ESC: back)`:
```
Hint / Hint col / Player + / P+ size / P+ col / Fix X / Fix Y / Capture / Frame / Pattern
```

| Key | Action |
|---|---|
| `↑` `↓` | move the cursor (wraps at both ends) |
| `←` `→` | change the value (hold for continuous fine steps; on a colour row it walks the presets) |
| `Z` | flip a switch row; `Capture` = capture once; `Seed` = digit entry; a colour row = hex entry; **`Hint` on the main menu = open the settings panel** |
| `ESC` | while typing = cancel; otherwise = back out of the settings panel |
| `F12` | open / close the whole overlay |
| while open | the game itself receives no input |

What the rows mean:

- **`Hint:`** — master switch for hint markers, default `on`
- **`Hint col:`** — the colour used by every hint line that names none
- **`Player +:`** — the player's judgement-point crosshair, default `on`
- **`P+ size:`** — crosshair arm length (1..64 logical pixels, default 4)
- **`P+ col:`** — crosshair colour
- **`Capture:`** — press Z to write the current position + time into this stage's txt
- **`Pattern:`** — read-only. Current boss pattern number (**0-based**); `-1` mid-stage
- **`Frame:`** — read-only. Current stage frame
- **`Hit:`** — read-only. Times hit (**reset on every stage entry**, including retries)
- **`Fix X:` / `Fix Y:`** — calibration for the judgement-point crosshair (next section)
- **`Seed:` / `Lock Seed:`** — RNG seed locking
- **`No Gameover:`** — invincibility
- **`Lock Power:`** (Le01 / Le02) or **`Lock P1:` + `Lock P2:`** (Le03) — frozen power.
  Le03 has two characters: `P1` freezes the main one and `P2` the partner, each latching
  the power you had at the moment you flipped it

### Using the colour rows (`Hint col` / `P+ col`)

- **`←` `→`** walk **12 presets**: white / pale yellow / red / orange / yellow /
  green / cyan / blue / violet / magenta / pink / grey.
- **`Z`** enters **hex entry**: type six digits of `RRGGBB`, exactly as you would
  write a colour on a web page (red = `FF0000`). The digits fill **from the left**,
  so typing F, F, 0, 0, 0, 0 shows `FF0000` the whole way. `BACK` removes one digit,
  `Z` commits, `ESC` restores the old value.
- The little **swatch** at the end of the row shows the current colour.
- `Hint col` applies to **every hint line that names no colour**; to give one line
  its own colour, add `R,G,B` at the end of that line (see section 3).

### Earthen Miraculous Sword (Le02) / Reactivate majestical imperial (Le03)

**All three games are now identical** — a main menu plus a 10-row hint settings panel,
the colour rows, the multi-key `prac.cfg` and the 1/8-unit `Fix X/Y` (see sections 6
and 8). The differences are **Le03's extra main-menu row** (two characters, so
`Lock Power` becomes `Lock P1` / `Lock P2`) plus each game's own quirks (Le03 has
stages 1..8 including Alpha, for instance).

> Older builds (Le02 before v0.7.12, Le03 before v0.5.15) used the flat 12-row menu:
> `No Gameover / Lock Power / Hint / Player + / Capture / Frame /
> Pattern / Lock Seed / Seed / Hit / Fix X / Fix Y`.
> Rows move around after upgrading, but the values in `prac.cfg` carry over
> (the key names did not change).
>
> Le03 up to v0.5.17 had a single `Lock Power` row that only froze the main
> character; from v0.5.18 it is `Lock P1` / `Lock P2`.

### Pause-menu hotkeys: `R` restart stage / `Q` back to title　★ all three games (Le03 v0.6.0 / Le02 v0.8.0 / Le01 v0.2.0 and up)

Pressing **ESC** in game opens the pause menu
(`Resume / Restart / Return to title / Quit`). Restarting or quitting used to mean
moving the cursor with the arrow keys, pressing Z, then picking "yes" in a
confirmation box and pressing Z again. **Now it is one key:**

| Key | Effect |
| --- | --- |
| **`R`** | restart the current stage immediately (same as `Restart` + confirm) |
| **`Q`** | go straight back to the title screen (same as `Return to title` + confirm) |

- **Only active while that pause menu is open.** Pressing `R` / `Q` during normal
  play, a boss fight or mid-stage does nothing at all and cannot disturb your run.
- **This is not a key macro.** The patch writes the game's own scene-phase variable,
  i.e. it takes exactly the same code path the menu takes after you confirm — so the
  menu does **not** flash and the cursor does **not** jump. Where the cursor happens
  to be makes no difference.
- Because it calls that path directly, there is no risk of the cursor sliding onto
  `Quit`: `R` / `Q` can only ever restart or return to the title.
- Quitting the game is still done through the menu's `Quit` item (deliberately not
  bound to a hotkey, to rule out accidents).

---

## 7. The `Player +` crosshair and `Fix X/Y`

- `Player +` draws **the player's judgement point**, using **the same coordinate
  transform as the hint markers**. So when you place a hint under your own feet,
  the two crosses **must coincide** — that is deliberate, and you can use it to check
  one against the other.
- **`P+ size`** is the arm length (logical pixels, 1..64, default 4). One logical
  pixel is about 3.33 screen pixels, so 4 draws roughly 27 screen pixels wide.
- **`P+ col`** is the crosshair colour (presets / hex entry, see section 6).
- If the crosshair is slightly off the little dot the game draws, fine-tune it with
  **`Fix X` / `Fix Y`**:

  | | all three games (Le01 v0.1.9 / Le02 v0.7.13 / Le03 v0.5.16 and up) |
  |---|---|
  | neutral (no shift) | **`128`** |
  | one step | **1/8 logical pixel** |
  | range | `0 .. 256` |

  > Le03 up to v0.5.14 used `64` / a quarter of a logical pixel / `0 .. 128`. The
  > neutral point moved to 128 with the new scale, but **no manual migration is
  > needed**: the old `prac.cfg` stored only `playerplus`, so it never held
  > `fixx` / `fixy` and you get the new neutral automatically.

  **Larger = further right / further down.**

- **★ Why 1/8 of a pixel is worth having**: `box()` only takes integers, so the
  *visible* position is always a whole logical pixel (about 3.33 screen pixels).
  What the finer step buys is control over **where the truncation boundary falls**.
  The player's own position is fractional, so if the game's judgement dot is drawn
  with round-to-nearest while we truncate, setting `Fix` to `132` (+0.5) makes the
  two coincide for **every** player position; a whole-pixel step can never do that.
  **8 steps = exactly one logical pixel** (measured: `Fix=128` -> x 332,
  `136` -> 333, `144` -> 334).
- **The hint markers follow the same calibration**, so you only align it once.
- **The calibration is saved to `prac.cfg`**, so you do not redo it every launch.

---

## 8. The settings file `prac.cfg`

Next to the exe, plain text, one setting per line, all values decimal:

```
playerplus=1
hint=1
hintcol=16744448
ppsize=4
ppcol=16777215
fixx=128
fixy=128
```

| Key | Menu row | Value |
|---|---|---|
| `playerplus` | `Player +` | 0 / 1 |
| `hint` | `Hint` | 0 / 1 |
| `hintcol` | `Hint col` | colour (decimal `RRGGBB`; white = 16777215, red = 16711680) |
| `ppsize` | `P+ size` | 1 .. 64 |
| `ppcol` | `P+ col` | colour |
| `fixx` | `Fix X` | 0 .. 256 |
| `fixy` | `Fix Y` | 0 .. 256 |

- **All three games remember these seven** (Le01 v0.1.9 / Le02 v0.7.13 /
  Le03 v0.5.15 and up).
- **No file = every built-in default**. Any change you make in the menu rewrites
  **the whole file** immediately.
- Delete `prac.cfg` to restore the factory defaults.
- **It is meant to be hand-editable**: edit, save, and it applies on the next launch.
  Lines and keys it does not recognise are ignored.
- A read-only game folder still plays fine — it just cannot remember settings.

---

## 9. Differences between the three games

All three share the **same** hint file format and the **same** F12 menu: a main table
plus a 10-row hint settings panel, the `Hint col` / `P+ size` / `P+ col` rows, the
optional 7th-9th `R,G,B` fields, the seven `prac.cfg` keys, and `Fix X/Y` at 1/8
logical pixel per step with 128 as neutral.

What genuinely differs is only this:

| | Le01 | Le02 | Le03 |
|---|---|---|---|
| hint folder | `<game folder>\hint\` | same | same |
| Main-menu rows | 6 | 6 | **7** (two characters: `Lock P1` + `Lock P2`) |
| Stage numbers | 1 .. 7 (Extra = 7) | 1 .. 7 | **1 .. 8** (stage 8 is Alpha) |
| Pattern table | see section 4; the mid-stage chapter table lives in the practice menu | Appendix A | Appendix B |
| Pause-menu hotkeys | **yes** (`R` restart / `Q` title, section 6.5) | same | same |
| Unique to it | Extra-boss bomb fix | replay settings / TAS tools | `prepareAlphaMusic` |

> Older builds (Le02 before v0.7.12, Le03 before v0.5.15) had a single-layer 12-row
> menu, hard-coded colours and a `prac.cfg` that held only `playerplus`. Upgrading
> brings all of that along, and **no manual migration is needed** -- those keys simply
> did not exist in the old file.

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
