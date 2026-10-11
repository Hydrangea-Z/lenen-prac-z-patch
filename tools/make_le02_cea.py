#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Produce our own Le02 (EMS / 连缘蛇丛剑) practice .cea from BAN's source.

BAN's file is never touched: we read it, apply anchored insertions, and write a
new .cea next to this project.  Every anchor is asserted, so if the upstream
source drifts the script fails loudly instead of silently mis-patching.

Same shape as make_prac2_cea.py (which does this for le03).  Feature groups:

  --bossfix   (default on)
      Replace `getBossExtraFlag` so it reads *our practice menu* instead of the
      boss object snapshot.  BAN's version inspects the boss object's +0x30/+0x34,
      which are copied when the boss spawns and are not a reliable source for
      "what is being practised", so the five `bossBombGate` hooks can fail to
      enable the immunity.  We OR in the menu state, which is the one true
      source for what is being practised:
          immune  <=>  practising stage index 6 (Extra)
                       AND difficulty is Extra (5) or AbsurdlyExtra (6)
      EasyExtra (4) deliberately still takes spell damage, matching the game.
      EMS has no EX+alpha stage, so unlike le03 there is only the one stage.

  --moderow   (default on)
      Add a `Mode: Boss / Section` row under `Stage`.  In Section mode the
      `Pattern` row becomes `Section: n` and selects a 道中 chapter, writing that
      chapter's frame into `Frame warp` and clearing the boss warp.
      Chapter tables come from data/le02_sections.json (EMS has 7 stages).

  --ui        (default on, needs --moderow)
      Menu polish:        * LEFT at the minimum wraps to the row's maximum, RIGHT at the maximum
          wraps back to the minimum.  Rows with no real upper bound (Frame,
          Score) keep clamping.
        * Boss mode freezes `Frame warp` (the frame belongs to the pattern and
          a mismatched frame desyncs the boss); Section mode lets the user edit
          it.
        * new editable `Life:` / `Bomb:` rows, capped at 9.
        * the menu's frame box is grown so it still contains the text now that
          three rows were added (8 -> 11 rows; box bottom 310 -> 327).
        * `Bomb:` starts at the character's real default (4 / 2 / 3 / 5).

  --overlay   (default on)
      The F12 in-game menu, available in every mode (v0.3.3), plus the first
      two features it drives (v0.4.0):
        * No Gameover (不疮): at 0 lives a hit respawns instead of ending the
          run.  Only the case that would have been a GAME OVER changes path,
          so a replay stays frame-accurate up to the first fatal hit.  It works
          by setting life to 1 and taking the respawn branch, which then does
          the game's own `dec [eax+0x48]` -- i.e. it looks exactly like
          "1 life hit down to 0 lives", and the owed lives are counted in
          NOSORE_DEBT.
          (Named "No Gameover", not "No Miss": it does not stop you being hit,
          it stops the hit from ending the run.)
        * freeze power: power is pinned, so neither pickups nor hits move it.
          There is no value to type in -- turning the switch on captures the
          power you have at that instant and holds it there (v0.4.2).  If you
          want a specific starting power, set it in the game's own practice
          menu first, then lock.  Implemented by taking over the clamp the game
          already runs once per frame, so it costs nothing extra.
      Both switches default to OFF, and both hooks re-run the original
      instructions when their switch is off, so with the menu untouched the
      game is byte-for-byte vanilla at those two sites.
      Rows: No Gameover / Lock Power / Seed / Debt / Slot 6.
      Sites: game+B980C (6 bytes, the game-over branch) and game+B9B05 (33
      bytes, the power clamp at the tail of the player update).

      Value editing (v0.4.1): a row is six dwords -- text, value pointer, min,
      max, step, wrap.  Tapping LEFT/RIGHT moves by `step`; holding it for
      ~0.33 s then moves by 1 about 20x/s, so a 0..500 row (Power) or a
      0..65535 row (Seed) can be set to an exact value.  `wrap` decides what
      happens at an end: 1 = jump to the other end (right for a 0/1 switch),
      0 = stop there (right for a wide range).

  --seed      (default on)
      Lock the RNG seed (v0.5.0).  The engine's RNG is a Mersenne Twister; the
      game derives a 32-bit seed from the system clock, parks it in a global,
      and re-seeds the MT from that global when the stage scene object is
      constructed -- i.e. once per *stage*, not once per run.
        * The seed global is read in exactly one place (game+B2BD0).
        * The seed wrapper has exactly one caller (game+B2BD9).
      Both facts come from a full .text sweep, which is what makes a single
      5-byte patch sufficient.  With SEED_ON = 0 the hook just forwards the
      game's own argument, so it is byte-equivalent to vanilla; with
      SEED_ON = 1 the seed becomes SEL_SEED.
      The hook also fingerprints the MT state right after seeding (16 dwords),
      which turns "same seed => same RNG" into something checkable.

  Player+     (v0.7.7, part of --overlay)
      The self-machine judgement-point crosshair, back-ported from le03's
      `Player +` row.  A new F12 row (default ON) draws a small 25x3 / 3x25
      cross at the player's judgement point during ordinary play.  It is
      gated by its OWN switch, not by Hint, and it is computed with exactly
      the same `pos + (Fix - 0x40) + HINT_OX/OY` transform the hint markers
      use -- so with Fix X/Y at 0x40 the cross sits on the dot AND on any
      hint marker placed there, and one Fix nudge moves both together.  That
      shared transform is the whole point: on le03 the two had drifted apart
      because the marker applied Fix twice and the hints not at all, and
      the user had to line them up by eye.

Usage:
    python make_le02_cea.py [--bossfix] [--moderow] [--ui] [--overlay] [--seed]
                            [--no-bossfix] [--no-moderow] [--no-ui]
                            [--no-overlay] [--no-seed]
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = "D:/STG/temp/Le02.cea"
DST = os.path.join(ROOT, "work", "Le02-prac.cea")
SECTIONS_JSON = os.path.join(ROOT, "data", "le02_sections.json")

# ---- chapter frames per stage (0-based stage index).
# Derived from data/le02_sections.json so the hex can never be hand-mistyped.
_doc = json.load(open(SECTIONS_JSON, encoding="utf-8"))
SECTIONS = {s["id"] - 1: [c["frame"] for c in s["chapters"]] for s in _doc["stages"]}
assert sorted(SECTIONS) == list(range(7)), "expected 7 stages"
for _s in _doc["stages"]:
    assert len(_s["chapters"]) == _s["chapter_count"], _s["label"]

EDITS = []


def sub(group, old, new, why):
    EDITS.append((group, old, new, why))


# =========================================================================== #
# Feature 1: boss spell immunity on the Extra stage
# =========================================================================== #
sub(
    "bossfix",
    "getBossExtraFlag:\n"
    "  mov al, [ebx+A1]\n"
    "  cmp dword ptr [IS_PRAC], 1\n"
    "  jne boss_extra_return\n"
    "  cmp dword ptr [ebx+30], 7\n"
    "  jl boss_extra_return\n"
    "  cmp dword ptr [ebx+30], 7\n"
    "  jg boss_extra_return\n"
    "  cmp dword ptr [ebx+34], 5\n"
    "  jl boss_extra_return\n"
    "  cmp dword ptr [ebx+34], 6\n"
    "  jg boss_extra_return\n"
    "  mov al, 1\n"
    "boss_extra_return:\n"
    "  ret\n",

    "getBossExtraFlag:\n"
    "  // ecx and edx are live at every bossBombGate site, so preserve them.\n"
    "  push ecx\n"
    "  push edx\n"
    "  mov al, [ebx+A1]\n"
    "  cmp dword ptr [IS_PRAC], 1\n"
    "  jne boss_extra_return\n"
    "  // Ground truth: what the practice menu is set to right now.\n"
    "  // Stage index 6 is the Extra stage; 5/6 are Extra / AbsurdlyExtra.\n"
    "  mov ecx, [SEL_STAGE]\n"
    "  cmp ecx, 6\n"
    "  jne boss_extra_scene\n"
    "  mov ecx, [SEL_DIFF]\n"
    "  cmp ecx, 5\n"
    "  jl boss_extra_scene\n"
    "  cmp ecx, 6\n"
    "  jg boss_extra_scene\n"
    "  mov al, 1\n"
    "  jmp boss_extra_return\n"
    "boss_extra_scene:\n"
    "  // BAN's boss-object snapshot test, kept as a second opinion.\n"
    "  cmp dword ptr [ebx+30], 7\n"
    "  jl boss_extra_return\n"
    "  cmp dword ptr [ebx+30], 7\n"
    "  jg boss_extra_return\n"
    "  cmp dword ptr [ebx+34], 5\n"
    "  jl boss_extra_return\n"
    "  cmp dword ptr [ebx+34], 6\n"
    "  jg boss_extra_return\n"
    "  mov al, 1\n"
    "boss_extra_return:\n"
    "  pop edx\n"
    "  pop ecx\n"
    "  ret\n",
    "read the practice menu state for boss immunity",
)

sub(
    "bossfix",
    "label(boss_extra_return)\n",
    "label(boss_extra_return)\nlabel(boss_extra_scene)\n",
    "declare boss_extra_scene",
)

# =========================================================================== #
# Feature 2: the Mode row (Boss / Section)
# =========================================================================== #
sub(
    "moderow",
    "label(TXT_SCORE)\n",
    "label(TXT_SCORE)\n"
    "label(SEL_MODE)\n"
    "label(SEL_SECTION)\n"
    "label(SECTION_CNT)\n"
    "label(SECTION_TABLE)\n"
    "label(sec_0)\nlabel(sec_1)\nlabel(sec_2)\nlabel(sec_3)\n"
    "label(sec_4)\nlabel(sec_5)\nlabel(sec_6)\n"
    "label(MODE_TXTS)\nlabel(mode_0)\nlabel(mode_1)\n"
    "label(TXT_MODE)\nlabel(TXT_SECTION)\n"
    "// (menu_vptr_ok used to be declared here, but the --ui block replaces the\n"
    "//  --moderow section-mode override that defined it.  Dropped so the\n"
    "//  declared-but-undefined check in cea.py stays meaningful.)\n"
    "label(draw_section)\nlabel(draw_row_done)\n"
    "label(callback_section)\nlabel(callback_sec_ok)\nlabel(callback_sec_none)\n",
    "declare the new labels",
)

sub(
    "moderow",
    "SEL_DATA:\n dw 6 0\n dw 6 0\n",
    "SEL_DATA:\n dw 6 0\n dw 1 0\n dw 6 0\n",
    "SEL_DATA gains the Mode entry",
)

sub(
    "moderow",
    "SEL_ARR_BEGIN:\nSEL_STAGE:\n  dd 0\nSEL_DIFF:\n",
    "SEL_ARR_BEGIN:\nSEL_STAGE:\n  dd 0\nSEL_MODE:\n  dd 0\nSEL_DIFF:\n",
    "SEL_MODE becomes row 2",
)

sub(
    "moderow",
    "SEL_ARR_LAST:\nSEL_SCORE:\n  dd 0\nCURR_SEL:\n",
    "SEL_ARR_LAST:\nSEL_SCORE:\n  dd 0\nSEL_SECTION:\n  dd 0\nCURR_SEL:\n",
    "SEL_SECTION storage after the last row",
)

sub(
    "moderow",
    "  movzx ebx, word ptr [esi]\n"
    "  movzx esi, word ptr [esi+2]\n"
    "\n"
    "  cmp esi, 0\n"
    "  je customMenu_slowInc\n",

    "  movzx ebx, word ptr [esi]\n"
    "  movzx esi, word ptr [esi+2]\n"
    "\n"
    "  // Section mode: the Pattern row edits the chapter index instead.\n"
    "  cmp dword ptr [SEL_MODE], 0\n"
    "  je menu_vptr_ok\n"
    "  cmp edi, PATTERN_WARP\n"
    "  jne menu_vptr_ok\n"
    "  mov eax, [SEL_STAGE]\n"
    "  movzx eax, byte ptr [SECTION_CNT+eax]\n"
    "  test eax, eax\n"
    "  jz menu_vptr_ok\n"
    "  mov edi, SEL_SECTION\n"
    "  mov ebx, eax\n"
    "  dec ebx\n"
    "  xor esi, esi\n"
    "menu_vptr_ok:\n"
    "\n"
    "  cmp esi, 0\n"
    "  je customMenu_slowInc\n",
    "section-mode value pointer override",
)

sub(
    "moderow",
    "customMenu_notLeft:\n  cmp [KEY_UP], 1\n",
    "customMenu_notLeft:\n  mov edi, [CURR_SEL]\n  cmp [KEY_UP], 1\n",
    "up/down must still move the cursor, not the value pointer",
)

sub(
    "moderow",
    "  add edi, 10\n"
    "\n"
    "  mov eax, [SEL_DIFF]\n"
    "  push [DIFF_TXTS+eax*4]\n",

    "  add edi, 10\n"
    "\n"
    "  mov eax, [SEL_MODE]\n"
    "  push [MODE_TXTS+eax*4]\n"
    "  push TXT_MODE\n"
    "  mov eax, SEL_MODE\n"
    "  call getColor\n"
    "  push eax\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  push edi\n"
    "  push 30\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  add edi, 10\n"
    "\n"
    "  mov eax, [SEL_DIFF]\n"
    "  push [DIFF_TXTS+eax*4]\n",
    "Mode row draw block",
)

sub(
    "moderow",
    "  mov eax, [SEL_STAGE]\n"
    "  mov ebx, [PATTERNS_TABLE+eax*4]\n"
    "  mov eax, [PATTERN_WARP]\n"
    "  mov ebx, [ebx+eax*4]\n"
    "  push ebx\n"
    "  push TXT_PATTERN\n"
    "  mov eax, PATTERN_WARP\n"
    "  call getColor\n"
    "  push eax\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  push edi\n"
    "  push 30\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  add edi, 10\n",

    "  cmp dword ptr [SEL_MODE], 0\n"
    "  jne draw_section\n"
    "  mov eax, [SEL_STAGE]\n"
    "  mov ebx, [PATTERNS_TABLE+eax*4]\n"
    "  mov eax, [PATTERN_WARP]\n"
    "  mov ebx, [ebx+eax*4]\n"
    "  push ebx\n"
    "  push TXT_PATTERN\n"
    "  mov eax, PATTERN_WARP\n"
    "  call getColor\n"
    "  push eax\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  push edi\n"
    "  push 30\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  add edi, 10\n"
    "  jmp draw_row_done\n"
    "draw_section:\n"
    "  mov eax, [SEL_SECTION]\n"
    "  inc eax\n"
    "  push eax\n"
    "  push TXT_SECTION\n"
    "  mov eax, PATTERN_WARP\n"
    "  call getColor\n"
    "  push eax\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  push edi\n"
    "  push 30\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  add edi, 10\n"
    "draw_row_done:\n",
    "Pattern row shows Section in section mode",
)

sub(
    "moderow",
    "customMenuSwitchClb:\n"
    "  mov eax, [CURR_SEL]\n"
    "  cmp eax, SEL_STAGE\n"
    "  jne callback_pattern\n"
    "  mov dword ptr [FRAME_COUNT_INIT], 0\n"
    "  mov dword ptr [PATTERN_WARP], 0\n"
    "callback_pattern:\n"
    "  mov eax, [SEL_STAGE]\n"
    "  movzx ebx, byte ptr [MAX_PATTERNID+eax]\n",

    "customMenuSwitchClb:\n"
    "  mov eax, [CURR_SEL]\n"
    "  cmp eax, SEL_STAGE\n"
    "  jne callback_pattern\n"
    "  mov dword ptr [FRAME_COUNT_INIT], 0\n"
    "  mov dword ptr [PATTERN_WARP], 0\n"
    "  mov dword ptr [SEL_SECTION], 0\n"
    "callback_pattern:\n"
    "  mov eax, [SEL_STAGE]\n"
    "  cmp dword ptr [SEL_MODE], 0\n"
    "  jne callback_section\n"
    "  movzx ebx, byte ptr [MAX_PATTERNID+eax]\n",
    "dispatch switchClb on mode",
)

sub(
    "moderow",
    "callback_none:\n"
    "  mov dword ptr [FRAME_COUNT_INIT], 0\n"
    "callback_done:\n"
    "  ret\n",

    "callback_none:\n"
    "  mov dword ptr [FRAME_COUNT_INIT], 0\n"
    "  jmp callback_done\n"
    "callback_section:\n"
    "  // Section mode: no boss warp, the frame comes from the chapter table.\n"
    "  mov dword ptr [PATTERN_WARP], 0\n"
    "  mov dword ptr [SELECTED_ID], ffffffff\n"
    "  mov dword ptr [SELECTED_PHASE], 0\n"
    "  movzx ebx, byte ptr [SECTION_CNT+eax]\n"
    "  test ebx, ebx\n"
    "  jz callback_sec_none\n"
    "  dec ebx\n"
    "  cmp [SEL_SECTION], ebx\n"
    "  jle callback_sec_ok\n"
    "  mov [SEL_SECTION], ebx\n"
    "callback_sec_ok:\n"
    "  mov ecx, [SEL_SECTION]\n"
    "  mov ebx, [SECTION_TABLE+eax*4]\n"
    "  mov ebx, [ebx+ecx*4]\n"
    "  mov [FRAME_COUNT_INIT], ebx\n"
    "  jmp callback_done\n"
    "callback_sec_none:\n"
    "  mov dword ptr [SEL_SECTION], 0\n"
    "  mov dword ptr [FRAME_COUNT_INIT], 0\n"
    "callback_done:\n"
    "  ret\n",
    "section branch of switchClb",
)


# =========================================================================== #
# Feature 3: menu polish
#   (a) LEFT at the minimum wraps to the row's maximum, for rows with a real
#       upper bound.  Frame and Score are unbounded (their SEL_DATA max is
#       FFFF) and keep clamping at zero, as asked.
#   (b) Boss mode freezes the frame (it belongs to the pattern); Section mode
#       lets the user edit it.
#   (c) new editable Life / Bomb rows.
# =========================================================================== #

# ---- (a) remember the effective maximum for the current row.
sub(
    "ui",
    "  movzx ebx, word ptr [esi]\n"
    "  movzx esi, word ptr [esi+2]\n"
    "\n"
    "  // Section mode: the Pattern row edits the chapter index instead.\n"
    "  cmp dword ptr [SEL_MODE], 0\n"
    "  je menu_vptr_ok\n"
    "  cmp edi, PATTERN_WARP\n"
    "  jne menu_vptr_ok\n"
    "  mov eax, [SEL_STAGE]\n"
    "  movzx eax, byte ptr [SECTION_CNT+eax]\n"
    "  test eax, eax\n"
    "  jz menu_vptr_ok\n"
    "  mov edi, SEL_SECTION\n"
    "  mov ebx, eax\n"
    "  dec ebx\n"
    "  xor esi, esi\n"
    "menu_vptr_ok:\n",

    "  movzx ebx, word ptr [esi]\n"
    "  movzx esi, word ptr [esi+2]\n"
    "\n"
    "  // The Pattern row is the only one whose real upper bound is dynamic:\n"
    "  // it is the last pattern of the stage, or the last chapter in Section\n"
    "  // mode.  Computing it here feeds both the clamp and the left-wrap.\n"
    "  cmp edi, PATTERN_WARP\n"
    "  jne menu_max_ok\n"
    "  mov eax, [SEL_STAGE]\n"
    "  cmp dword ptr [SEL_MODE], 0\n"
    "  jne menu_sec_max\n"
    "  movzx ebx, byte ptr [MAX_PATTERNID+eax]\n"
    "  jmp menu_max_ok\n"
    "menu_sec_max:\n"
    "  movzx ebx, byte ptr [SECTION_CNT+eax]\n"
    "  test ebx, ebx\n"
    "  jz menu_max_ffff\n"
    "  mov edi, SEL_SECTION\n"
    "  dec ebx\n"
    "  xor esi, esi\n"
    "  jmp menu_max_ok\n"
    "menu_max_ffff:\n"
    "  mov ebx, ffff\n"
    "menu_max_ok:\n"
    "  mov [SEL_MAX], ebx\n",
    "effective max for the current row (+ section override)",
)

# ---- (a) the wrap itself, both directions.
sub(
    "ui",
    "  sub [edi], ecx\n"
    "  cmp [edi], 0\n"
    "  jnl customMenu_leftClb // not <zero\n"
    "  mov [edi], 0\n"
    "customMenu_leftClb:\n",

    "  sub [edi], ecx\n"
    "  cmp [edi], 0\n"
    "  jnl customMenu_leftClb // not <zero\n"
    "  // Under the minimum: bounded rows wrap to the top, unbounded ones\n"
    "  // (max == FFFF, i.e. Frame and Score) just clamp at zero.\n"
    "  mov eax, [SEL_MAX]\n"
    "  cmp eax, ffff\n"
    "  je customMenu_leftZero\n"
    "  mov [edi], eax\n"
    "  jmp customMenu_leftClb\n"
    "customMenu_leftZero:\n"
    "  mov [edi], 0\n"
    "customMenu_leftClb:\n",
    "left at minimum wraps to maximum",
)

sub(
    "ui",
    "  add [edi], ecx\n"
    "  cmp ebx, ffff\n"
    "  je customMenu_rightClb\n"
    "  cmp [edi], ebx\n"
    "  jna customMenu_rightClb // does not exceed max\n"
    "  mov [edi], ebx\n"
    "customMenu_rightClb:\n",

    "  add [edi], ecx\n"
    "  cmp ebx, ffff\n"
    "  je customMenu_rightClb\n"
    "  cmp [edi], ebx\n"
    "  jna customMenu_rightClb // does not exceed max\n"
    "  // Over the maximum: wrap to the bottom.  Unbounded rows (max ==\n"
    "  // FFFF) never reach here, so they keep their plain clamp.\n"
    "  mov dword ptr [edi], 0\n"
    "customMenu_rightClb:\n",
    "right at maximum wraps to minimum",
)

# ---- (d) the menu frame box.
#
# The screen our hook lives on (game+74112) is the game's own list screen --
# the one that prints "  *STAGE SELECT*  ".  Before it draws the list it draws
# the list's frame:
#
#   game+73F61  cmp dword ptr [ebx+0x624], 0xa   ; list length
#   game+73F6F  jge game+74046                   ; >= 10 -> fixed rect
#   ... count < 10 branch: rect = (2D,8C, count*22.5+45, count*17+140)
#   game+74046  ...                              ; fixed-rect branch
#   game+7405F  push 0x136                       ; bottom = 310
#   game+74064  push 0x10e                       ; right  = 270
#   game+74069  push 0x8c                        ; top    = 140
#   game+7406e  push 0x2d                        ; left   = 45
#   game+74070  call game+4d1010                 ; black frame
#   ... the same rect again in white at game+7409B..0x740AC
#
# A screenshot of BAN's le02 practice menu measures the drawn box at exactly
# (45,140)-(270,310), i.e. the fixed-rect branch -- so the list length here is
# >= 10 and the frame is a fixed 310 tall no matter how many rows we draw.
#
# The rect is in the game's 640x480 space, and so is our menu text -- every
# numeric literal in this .cea is HEXADECIMAL, so `mov edi, 90` is 0x90 = 144
# and `add edi, 10` is 0x10 = 16.  Row i therefore sits at y = 144 + 16*i, the
# 11th row lands on 304 and its glyphs end around 318.  The stock box stops at
# 310, which is why it used to cut the list off right after `Petals:` (with the
# original 8 rows the last row was at 144 + 16*7 = 256 and fitted fine).
#
# Two changes:
#   1. force the fixed-rect branch (the list length on this screen is not ours
#      to rely on), and
#   2. stretch that fixed rect to 327 = 11*17 + 140, the value the count<10
#      formula itself would produce for 11 rows.
sub(
    "ui",
    "game+74112:\n jmp customMenuRender\n",
    "game+73F67:\n"
    " db 00 // cmp [ebx+624], 0 -- always take the fixed-rect branch\n"
    "game+7405F:\n"
    " db 68 47 01 00 00 // push 0x147 -- frame bottom 327 (was 310)\n"
    "game+7409B:\n"
    " db 68 47 01 00 00 // push 0x147 -- second (white) frame pass\n"
    "game+74112:\n jmp customMenuRender\n",
    "grow the menu frame so it contains all eleven rows",
)

sub(
    "ui",
    "game+74112:\n db 68 d0 9c 83 00\n",
    "game+73F67:\n db 0a\n"
    "game+7405F:\n db 68 36 01 00 00\n"
    "game+7409B:\n db 68 36 01 00 00\n"
    "game+74112:\n db 68 d0 9c 83 00\n",
    "restore the frame-geometry bytes",
)

# ---- (e) the initial Bomb count follows the character.
#
# game+ADDFEC is the selected character, right after the difficulty global at
# game+ADDFE8 -- the same (difficulty, character) pair of dwords le03 has at
# game+B0A53C / game+B0A540, and the same pair the player-manager ctor copies
# out of the game-state object at game+B8E64/B8EC5.  The per-character default
# bombs are the table the ctor builds at manager+0xA8..0xB4, which is exactly
# 4, 2, 3, 5 -- the numbers 燕樂玄鳥 / 宿祢&八尾呂智 / 黑巫鳥&蛇穴丸 / 雀巳组
# have in game.
sub(
    "ui",
    "define(getInput,game+74510)\n",
    "define(CHAR_IDX,game+ADDFEC)\n"
    "define(getInput,game+74510)\n",
    "the selected-character global",
)

sub(
    "ui",
    "label(TXT_SCORE)\n",
    "label(TXT_SCORE)\n"
    "label(BOMB_DEF)\nlabel(LAST_CHAR)\nlabel(menu_char_done)\n"
    "label(WRAP_LOCK)\nlabel(WRAP_TIMER)\n"
    "label(wrap_latch)\nlabel(wrap_latch_ret)\n"
    "label(wrap_release)\nlabel(wrap_no_lock)\n",
    "declare the character-default and wrap-dwell labels",
)

sub(
    "ui",
    "customMenuRender:\n"
    "  pushfd\n"
    "  pushad\n"
    "  call getInput\n",

    "customMenuRender:\n"
    "  pushfd\n"
    "  pushad\n"
    "  // Start `Bomb:` at the selected character's real default.  Re-applied\n"
    "  // whenever the character changes, so it is also correct if the player\n"
    "  // backs out and picks somebody else.\n"
    "  mov eax, [CHAR_IDX]\n"
    "  cmp eax, [LAST_CHAR]\n"
    "  je menu_char_done\n"
    "  mov [LAST_CHAR], eax\n"
    "  cmp eax, 3\n"
    "  ja menu_char_done\n"
    "  mov eax, [BOMB_DEF+eax*4]\n"
    "  mov [SEL_BOMB], eax\n"
    "menu_char_done:\n"
    "  call getInput\n",
    "initial Bomb follows the character",
)

# ---- (f) wrap dwell.
#
# `[KEY_LEFT]` / `[KEY_RIGHT]` are key *repeat counters*, not booleans.  A slow
# row passes `cmp ecx, eax` only when the counter is exactly 1, so it already
# needs a fresh press for every single step -- which is why wrapping never felt
# wrong there.  A fast row (Frame / Power / Flashbomb / Petals / Score) uses
# eax = FFFFFFFF, so the whole counter is added every frame; the moment it
# wraps onto an extreme the still-held key keeps subtracting and the value
# slides straight back off it.
#
# So: after a wrap on a fast row, freeze left/right for a short dwell.  Normal
# continuous adjustment is untouched -- the freeze only ever follows a jump.
sub(
    "ui",
    "customMenu_keyCheck:\n"
    "  mov ecx, [KEY_RIGHT]\n",

    "customMenu_keyCheck:\n"
    "  // Wrap dwell: the value has just landed on an extreme, so give the\n"
    "  // player a moment to let go before the held key can move it again.\n"
    "  cmp dword ptr [WRAP_LOCK], 0\n"
    "  je wrap_no_lock\n"
    "  cmp dword ptr [WRAP_TIMER], 0\n"
    "  jz wrap_release\n"
    "  dec dword ptr [WRAP_TIMER]\n"
    "  jmp customMenu_notLeft\n"
    "wrap_release:\n"
    "  mov dword ptr [WRAP_LOCK], 0\n"
    "wrap_no_lock:\n"
    "  mov ecx, [KEY_RIGHT]\n",
    "wrap dwell gates left/right",
)

sub(
    "ui",
    "  mov dword ptr [edi], 0\n"
    "customMenu_rightClb:\n",
    "  mov dword ptr [edi], 0\n"
    "  call wrap_latch\n"
    "customMenu_rightClb:\n",
    "arm the dwell after a right-wrap",
)

sub(
    "ui",
    "  mov [edi], eax\n"
    "  jmp customMenu_leftClb\n"
    "customMenu_leftZero:\n",
    "  mov [edi], eax\n"
    "  call wrap_latch\n"
    "  jmp customMenu_leftClb\n"
    "customMenu_leftZero:\n",
    "arm the dwell after a left-wrap",
)

# ---- (b) boss mode: keep the frame glued to the pattern.
sub(
    "ui",
    "  mov ebx, [CURR_SEL]\n"
    "  cmp ebx, PATTERN_WARP\n"
    "  jne callback_done\n"
    "  cmp edx, 0\n",

    "  // Boss mode: the frame is part of the pattern, and a frame that does\n"
    "  // not match the pattern desyncs the boss and can crash the game, so\n"
    "  // re-derive it on every change -- that makes the Frame row read-only.\n"
    "  cmp edx, 0\n",
    "boss mode freezes the frame",
)

# ---- (b) section mode: the user owns the frame.
sub(
    "ui",
    "callback_section:\n"
    "  // Section mode: no boss warp, the frame comes from the chapter table.\n"
    "  mov dword ptr [PATTERN_WARP], 0\n",

    "callback_section:\n"
    "  // Section mode: the frame is the user's to nudge; only re-derive it\n"
    "  // when something other than the Frame row changed.\n"
    "  cmp dword ptr [CURR_SEL], FRAME_COUNT_INIT\n"
    "  je callback_done\n"
    "  mov dword ptr [PATTERN_WARP], 0\n",
    "section mode allows editing the frame",
)

# ---- (c) Life / Bomb rows.
sub(
    "ui",
    "label(TXT_SCORE)\n",
    "label(TXT_SCORE)\n"
    "label(SEL_MAX)\nlabel(SEL_LIFE)\nlabel(SEL_BOMB)\n"
    "label(TXT_LIFE)\nlabel(TXT_BOMB)\n"
    "label(menu_max_ok)\nlabel(menu_sec_max)\nlabel(menu_max_ffff)\n"
    "label(customMenu_leftZero)\n"
    "label(life_stub)\nlabel(bomb_stub)\n"
    "label(life_stub_orig)\nlabel(bomb_stub_orig)\n"
    "label(life_stub_ret)\nlabel(bomb_stub_ret)\n",
    "declare the menu-polish labels",
)

sub(
    "ui",
    "assert(cave+3FF0,",
    "assert(game+B902B,c7 40 48 09 00 00 00)\n"
    "assert(game+B9064,8b 84 83 a8 00 00 00)\n"
    "assert(game+73F67,0a)\n"
    "assert(game+7405F,68 36 01 00 00)\n"
    "assert(game+7409B,68 36 01 00 00)\n"
    "assert(cave+3FF0,",
    "pin the two player-init sites and the menu-box geometry",
)

sub(
    "ui",
    "game+B9091:\n"
    " jmp setScore\n"
    " nop\n"
    " nop\n"
    "game+B9098:\n",

    "game+B902B:\n"
    " jmp life_stub\n"
    " nop\n"
    " nop\n"
    "game+B9032:\n"
    "life_stub_ret:\n"
    "game+B9064:\n"
    " jmp bomb_stub\n"
    " nop\n"
    " nop\n"
    "game+B906B:\n"
    "bomb_stub_ret:\n"
    "game+B9091:\n"
    " jmp setScore\n"
    " nop\n"
    " nop\n"
    "game+B9098:\n",
    "hook the player-init life/bomb writes",
)

# Keep the [DISABLE] section in step so the source still round-trips in CE.
sub(
    "ui",
    "game+B9091:\n"
    " db c7 40 58 00 00 00 00\n",
    "game+B902B:\n"
    " db c7 40 48 09 00 00 00\n"
    "game+B9064:\n"
    " db 8b 84 83 a8 00 00 00\n"
    "game+B9091:\n"
    " db c7 40 58 00 00 00 00\n",
    "restore bytes for the new sites",
)

sub(
    "ui",
    "  mov edx, [SEL_RESOURCE]\n"
    "  mov [eax+8C], edx\n"
    "power_done:\n",

    "  mov edx, [SEL_RESOURCE]\n"
    "  mov [eax+8C], edx\n"
    "  mov edx, [SEL_LIFE]\n"
    "  mov [eax+48], edx\n"
    "  mov edx, [SEL_BOMB]\n"
    "  mov [eax+60], edx\n"
    "power_done:\n",
    "setPower writes life and bomb",
)

sub(
    "ui",
    " dw 1388 1\n dw FFFF 1\n",
    " dw 1388 1\n dw 9 0\n dw 9 0\n dw FFFF 1\n",
    "SEL_DATA gains Life and Bomb",
)

sub(
    "ui",
    "SEL_RESOURCE:\n  dd 0\nSEL_ARR_LAST:\n",
    "SEL_RESOURCE:\n  dd 0\n"
    "SEL_LIFE:\n  dd 9\n"
    "SEL_BOMB:\n  dd 4\n"
    "SEL_ARR_LAST:\n",
    "Life and Bomb become rows",
)

sub(
    "ui",
    "CURR_SEL:\n  dd 0\nIS_PRAC:\n",
    "CURR_SEL:\n  dd 0\nSEL_MAX:\n  dd 0\nIS_PRAC:\n",
    "scratch slot for the current row's maximum",
)

sub(
    "ui",
    "  push [SEL_RESOURCE]\n"
    "  push TXT_RESOURCE\n"
    "  mov eax, SEL_RESOURCE\n"
    "  call getColor\n"
    "  push eax\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  push edi\n"
    "  push 30\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  add edi, 10\n"
    "\n"
    "  mov eax, [SEL_SCORE]\n",

    "  push [SEL_RESOURCE]\n"
    "  push TXT_RESOURCE\n"
    "  mov eax, SEL_RESOURCE\n"
    "  call getColor\n"
    "  push eax\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  push edi\n"
    "  push 30\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  add edi, 10\n"
    "\n"
    "  push [SEL_LIFE]\n"
    "  push TXT_LIFE\n"
    "  mov eax, SEL_LIFE\n"
    "  call getColor\n"
    "  push eax\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  push edi\n"
    "  push 30\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  add edi, 10\n"
    "\n"
    "  push [SEL_BOMB]\n"
    "  push TXT_BOMB\n"
    "  mov eax, SEL_BOMB\n"
    "  call getColor\n"
    "  push eax\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  push edi\n"
    "  push 30\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  add edi, 10\n"
    "\n"
    "  mov eax, [SEL_SCORE]\n",
    "Life and Bomb draw rows",
)

# ---- the cave-side stubs for the two new patch sites.
sub(
    "ui",
    "getBossExtraFlag:\n",

    "// The game has two player-init paths and we do not know which one runs\n"
    "// last, so write Life/Bomb in both -- setPower above, and these two.\n"
    "life_stub:\n"
    "  cmp dword ptr [IS_PRAC], 1\n"
    "  jne life_stub_orig\n"
    "  push edx\n"
    "  mov edx, [SEL_LIFE]\n"
    "  mov [eax+48], edx\n"
    "  pop edx\n"
    "  jmp life_stub_ret\n"
    "life_stub_orig:\n"
    "  mov dword ptr [eax+48], 9\n"
    "  jmp life_stub_ret\n"
    "bomb_stub:\n"
    "  cmp dword ptr [IS_PRAC], 1\n"
    "  jne bomb_stub_orig\n"
    "  mov eax, [SEL_BOMB]\n"
    "  jmp bomb_stub_ret\n"
    "bomb_stub_orig:\n"
    "  mov eax, [ebx+eax*4+A8]\n"
    "  jmp bomb_stub_ret\n"
    "wrap_latch:\n"
    "  // esi still holds this row's SEL_DATA fast flag.  Only the\n"
    "  // hold-to-scroll rows need the dwell; a slow row already needs a fresh\n"
    "  // key press for every single step, so it cannot run away on its own.\n"
    "  cmp esi, 0\n"
    "  je wrap_latch_ret\n"
    "  mov dword ptr [WRAP_LOCK], 1\n"
    "  mov dword ptr [WRAP_TIMER], 12 // 18 frames, about 0.3 s\n"
    "wrap_latch_ret:\n"
    "  ret\n"
    "getBossExtraFlag:\n",
    "life/bomb stubs and the wrap dwell",
)


# =========================================================================== #
# Feature 4: the F12 overlay  (v0.3.3) + No-Miss / freeze-power  (v0.4.0)
# =========================================================================== #
# A per-frame overlay menu that is available in *every* mode, not just the
# practice stage-select screen -- so the later features (No-Miss, lock power,
# seed select, hints) can be driven while actually playing.
#
# ---------------------------------------------------------------------------
# v0.4.0 -- the first two features wired to the menu.  Both are *code* hooks,
# not "rewrite the value every frame":
#
#   No-Miss (不疮)   game+B980C, 6 bytes.  This is the `cmp [player+0x48],0 /
#                    jg respawn` that chooses between respawning and GAME
#                    OVER.  The check runs BEFORE the shared `dec
#                    [player+0x48]` at game+B9894, and nothing reads the field
#                    in between, so handing the game a life of 1 makes the
#                    decrement land exactly on 0.  Lives never go negative and
#                    the HUD simply stays at 0.
#                    Crucially, only the case that would have been a GAME OVER
#                    changes path -- so a replay stays frame-accurate right up
#                    to the first fatal hit.  (See plan-nomiss-lockpower.md.)
#
#   freeze power     game+B9B05, 33 bytes.  The whole vanilla `clamp power
#                    into [0,500]` block at the tail of the player update.
#                    That block already runs once per frame, so taking it over
#                    costs nothing extra -- we replace an existing write
#                    rather than adding one.  With the lock on we store the
#                    chosen value instead, making power genuinely static.
#
# ---------------------------------------------------------------------------
# History of the overlay itself, because every wrong turn is a trap worth
# remembering:
#
#   v0.3.0  hooked game+CFAF0, which turned out to be the game's *shutdown*
#           routine (its tail is UnregisterClassW(hInstance, className)), so
#           pressing F12 did nothing at the title screen.
#   v0.3.1  hooked the real per-frame driver game+CFF70 (every caller loops on
#           it, e.g. `... ; call 0x4CFF70 ; test eax,eax ; jne done ; ...`),
#           but drew from the *end* of the frame (game+D04B7) -- too late.
#   v0.3.2  same hook, still nothing visible.
#
# The v0.3.1/v0.3.2 failure is now understood: by the time the frame function
# returns, the renderer has already been torn down.  Measured live at the title
# screen: [0x9EFD08]=0, [0x9EFE04]=0 (the `box` helper needs 3), [0x9EFAFC]=1
# (it needs 0), and the surface struct at [0x9EFB38] is all zeros.  So `box`
# and `drawTextTexture` silently bailed out and drew nothing.
#
# v0.3.3 therefore draws from the *entry* of the present function, the one
# point where the game's own helpers are still usable and nothing has been
# blitted yet:
#
#   game+14BD50  RVA 0x14BD50, reached from RVA 0xDF810 <- RVA 0xE27D0.  Its
#                prologue is 9 bytes (55 8B EC 81 EC CC 04 00 00); we redirect
#                it at one wrapper that draws, then re-executes the prologue
#                and jumps back to game+14BD59.
#                NOTE: RVA 0x14C310 (a `sub esp,0x548` function with 11 call
#                sites) is a *different*, text/console overlay layer.  It is
#                not the present path -- do not hook it.
#
# Three hook families, all inside that frame:
#
#   game+CFFCD  10 bytes into the frame function, right after its stack-cookie
#               prologue and its re-entrancy guard.  Runs *before* the frame's
#               update and render, so the menu logic lives here.
#   game+CF7CD  the `call game+140CD0` that refreshes the keyboard.  There are
#               four such sites (CF255 / CF2B5 / CF445 / CF7CD) and all four
#               are redirected at one wrapper, which runs the real input
#               function and then wipes the game's key array when the menu is
#               open.  KEYSHADOW is the only thing gameplay reads, so this is
#               a complete input suppression -- *after* the current frame has
#               already seen the key, so the menu stays usable.
#   game+14BD50 the present function's entry (see above).  Drawing here lands
#               on top of the finished frame because the blit comes later.
#
# Key state comes from the game's own GetKeyboardState import, so no injection
# and no new imports are needed.  VK codes we care about: F12=7B, UP=26,
# DOWN=28, LEFT=25, RIGHT=27.
#
# The PRB_* slots are a permanent diagnostic block at cave+0x3000; an external
# tool can poll them with ReadProcessMemory to prove which hooks fire.
#   cave+0x3000 PRB_FRAMES  frames seen at the entry hook
#   cave+0x3004 PRB_INPUT   times the input wrapper ran
#   cave+0x3008 PRB_BLIT    times overlay_draw ran (a draw "blit")
#   cave+0x300C PRB_F12     last raw F12 byte from GetKeyboardState
#   cave+0x3010 PRB_F12N    F12 rising edges seen
#   cave+0x3014 PRB_OPEN    mirror of OVERLAY_OPEN
#   cave+0x3018 PRB_PRES    times the present hook ran
OVERLAY_LABELS = [
    "overlay_entry", "overlay_input", "overlay_logic", "overlay_draw",
    "ovl_in_done", "ovl_in_clear",
    "ovl_toggle_done", "ovl_logic_done", "ovl_menu_open",
    "ovl_up_done", "ovl_down_done", "ovl_left_done", "ovl_right_done",
    "ovl_move_up", "ovl_move_down", "ovl_move_left", "ovl_move_right",
    "ovl_up_ok", "ovl_down_ok", "ovl_move_blocked",
    "ovl_row", "ovl_apply", "ovl_apply_hi_clamp", "ovl_apply_lo", "ovl_apply_lo_clamp",
    "ovl_apply_store", "ovl_nudge_right", "ovl_nudge_left", "ovl_reset_hold",
    "ovl_hold_not_right", "ovl_hold_check", "ovl_hold_new", "ovl_hold_left",
    "ovl_hold_none", "ovl_hold_done",
    "ovl_type_keys", "ovl_type_z_done", "ovl_type_esc_done", "ovl_type_back_done",
    "ovl_type_digit_loop", "ovl_type_digit_next", "ovl_type_digits_done",
    "ovl_type_toggle", "ovl_type_toggle_done", "ovl_type_commit",
    "ovl_type_exit", "ovl_type_cancel",
    "ovl_type_try_capture", "ovl_type_switch", "ovl_type_try_seed",
    "ovl_type_cancel_done", "ovl_type_append", "ovl_type_app_shift",
    "ovl_type_app_room", "ovl_type_app_done",
    "ovl_seedsw_done",
    "ovl_draw_row", "ovl_draw_done", "ovl_getColor", "ovl_color_sel",
    "OVERLAY_OPEN", "OVL_DRAWN", "OVL_CUR", "OVL_ROWS_N", "OVL_PREV_F12", "OVL_PREV_KEYS",
    "OVL_VKBUF", "OVL_ROWS", "OVL_ALT",
    "OVL_HOLD_DIR", "OVL_HOLD_N", "OVL_NUDGE_N", "OVL_HOLD_DELAY", "OVL_NUDGE_EVERY",
    "OVL_RCUR", "OVL_RPTR", "OVL_RY", "OVL_RTXT",
    "ovl_pick_alt", "ovl_pick_plain", "ovl_pick_done",
    "ovl_boss_poll", "ovl_boss_clear", "ovl_boss_done",
    "ovl_boss_zero", "ovl_boss_have", "ovl_boss_mirror",
    "ovl_boss_same_fight", "ovl_boss_tick", "ovl_boss_suppress",
    "HINT_PAT_IDX", "HINT_PAT_ON", "HINT_PAT_FRAME",
    "HINT_PAT_WAS", "HINT_PAT_LAST", "HINT_PAT_SKIP",
    "OVL_TYPE_ON", "OVL_TYPE_OLD", "OVL_TYPE_FRESH", "OVL_TYPE_LAST", "OVL_PREV_SEEDSW",
    "OVL_V_NOGAMEOVER", "OVL_V_LOCKPWR", "OVL_V_DEBT",
    "OVL_V_HINT", "OVL_V_PCROSS", "OVL_V_CAPTURE", "OVL_V_FRAME", "OVL_V_PATTERN", "DBG_STAGE",
    "TXT_OVL_PATTERN", "OVL_TYPE_ROW",
    "HINT_OX", "HINT_OY", "HINT_SIZE", "HINT_CX", "HINT_CY", "HINT_HALF",
    "DBG_PX", "DBG_PY", "draw_hints", "draw_hints_done",
    "draw_pcross", "ovl_pc_done",
    "load_hints", "load_hints_done", "load_hints_scan", "load_hints_next",
    "load_hints_loop", "load_hints_skip", "load_hints_want", "load_hints_selstage",
    "load_hints_cut", "load_hints_p1", "load_hints_dig", "load_hints_p2",
    "draw_hints_dash", "draw_hints_dash_len", "draw_hints_dash_loop",
    "draw_hints_dash_seg", "draw_hints_col",
    "draw_hints_vline", "draw_hints_vl_len", "draw_hints_vl_loop",
    "draw_hints_vl_seg",
    "draw_hints_loop", "draw_hints_next", "draw_hints_adx", "draw_hints_ady",
    "draw_hints_char_ok",
    "draw_hints_boss", "draw_hints_boss_start", "draw_hints_boss_end",
    "draw_hints_boss_ok",
    "hint_emit_time", "hint_emit_abs",
    "HINT_C_KIND", "HINT_C_PID", "HINT_C_PF",
    "HINT_C_EKIND", "HINT_C_EPID", "HINT_C_EF",
    "HINT_PATHW", "HINT_PRE", "HINT_SUF", "HINT_BUF", "HINT_BUFMAX",
    "HINT_HANDLE", "HINT_GOT", "HINT_LEN", "HINT_SYM", "HINT_COL",
    "HINT_COL_DIM", "HINT_FADE_R", "HINT_DASH", "HINT_USECOL", "HINT_DX", "HINT_DY", "TXT_OVL_FIX_X", "TXT_OVL_FIX_Y",
    "HINT_DASHLEN", "HINT_DASHEND",
    "HINT_P", "HINT_END", "HINT_CURSTAGE", "HINT_WANT", "HINT_N",
    "HINT_MAXN", "HINT_SKIP", "HINT_TOK", "HINT_ARR",
    "HINT_E_MARK", "HINT_E_SIZE", "HINT_E_CHAR", "HINT_E_X", "HINT_E_Y",
    "HINT_E_SK", "HINT_E_SP", "HINT_E_SF", "HINT_E_EK", "HINT_E_EP", "HINT_E_EF",
    "HINT_TKIND", "HINT_TPAT", "HINT_TFR", "HINT_CUR", "HINT_ROW",
    "HINT_C_X", "HINT_C_Y", "HINT_C_F", "HINT_CHAP_END", "HINT_IEDI",
    "HINT_CAPLEN", "HINT_CAPLEN2", "HINT_WROTE", "HINT_CAP_OK",
    "HINT_LINE", "HINT_LINE2", "HINT_LASTCH", "OVL_PREV_CAP",
    "hint_itoa", "hint_itoa_loop", "hint_itoa_pop", "hint_itoa_out",
    "hint_chapter_end", "hint_chap_ok", "hint_chap_loop", "hint_chap_hit",
    "hint_chap_out", "hint_chap_fin",
    "hint_capture", "hint_capture_done", "hint_capture_seek", "ovl_cap_done",
    "hint_cap_path", "hint_cp_copy", "hint_cp_num", "hint_cp_digit", "hint_cp_done",
    "hint_cap_form_done", "hint_cap_ensure_nl",
    "HINT_GLOB", "HINT_FIND", "HINT_FH", "HINT_PRELEN", "HINT_OK",
    "hint_build_path", "hint_bp_copy", "hint_bp_name", "hint_bp_done",
    "hint_diff_ok", "hint_diff_scan", "hint_diff_next", "hint_diff_easy",
    "hint_diff_normal", "hint_diff_hard", "hint_diff_unreal",
    "hint_diff_cmp", "hint_diff_have", "hint_diff_no", "hint_diff_none",
    "hint_diff_out", "hint_read_one", "hint_read_done",
    "hint_skip", "hint_skip_loop", "hint_skip_adv", "hint_skip_comment",
    "hint_skip_done", "hint_tok", "hint_tok_loop", "hint_tok_adv",
    "hint_tok_done", "hint_atoi", "hint_atoi_loop", "hint_atoi_done",
    "hint_time", "hint_time_num", "hint_store",
    "parse_hints", "parse_loop", "parse_done", "parse_hint",
    "parse_char_done", "parse_skip", "parse_not_stage", "parse_stage_word",
    "ovl_draw_panel", "ovl_frame_done",
    "TXT_OVL_TITLE", "TXT_OVL_NOGAMEOVER", "TXT_OVL_LOCKPWR", "TXT_OVL_LOCKSEED",
    "TXT_OVL_DEBT", "TXT_OVL_SEED", "TXT_OVL_SEED_EDIT",
    "TXT_OVL_HINT", "TXT_OVL_CAPTURE", "TXT_OVL_FRAME",
    "TXT_OVL_PCROSS", "ALT_PCROSS", "TXT_PCROSS_OFF", "TXT_PCROSS_ON",
    "cfg_path", "cfg_path_cut", "cfg_path_cp", "cfg_path_done",
    "cfg_load", "cfg_len_ok", "cfg_scan", "cfg_cmp", "cfg_cmp_no",
    "cfg_apply", "cfg_load_done", "cfg_save", "cfg_save_cp", "cfg_save_done",
    "cfg_tick", "cfg_tick_chk", "cfg_tick_done",
    "CFG_TAILW", "CFG_KEY", "CFG_PATHW", "CFG_BUF", "CFG_LINE",
    "CFG_H", "CFG_RD", "CFG_LEN", "CFG_VAL", "CFG_LOADED", "CFG_LAST", "CFG_WROTE",
    "ALT_NOGAMEOVER", "ALT_LOCKPWR", "ALT_HINT", "ALT_LOCKSEED",
    "TXT_NOGAMEOVER_OFF", "TXT_NOGAMEOVER_ON",
    "TXT_LOCKPWR_OFF", "TXT_LOCKPWR_ON",
    "TXT_HINT_OFF", "TXT_HINT_ON",
    "TXT_LOCKSEED_OFF", "TXT_LOCKSEED_ON",
    "PRB_FRAMES", "PRB_INPUT", "PRB_BLIT", "PRB_F12", "PRB_F12N", "PRB_OPEN",
    "PRB_PRES", "PRB_NOGAMEOVER", "PRB_LP",
    "overlay_present", "ovl_pres_done",
]

# v0.4.0: the two game-side hooks.  `nogameover_hook` replaces the game-over
# branch at game+B980C, `ovl_lockpower` takes over the per-frame power clamp at
# game+B9B05.  Both fall back to the original instructions when their switch is
# off, so the cave is a strict superset of the vanilla code path.
# v0.4.2: the lock has no value to type in -- it captures the live power into
# OVL_LP_TARGET on the first frame after the switch goes on.
HOOK_LABELS = [
    "nogameover_hook", "nogameover_vanilla", "nogameover_count", "NOSORE_DEBT",
    "ovl_lockpower", "ovl_lp_on", "ovl_lp_pin", "ovl_lp_vanilla",
    "ovl_lp_hi", "ovl_lp_done",
    "OVL_LP_TARGET", "OVL_LP_HELD",
    "DBG_PLAYER",
]

# v0.5.0: the RNG seed.  `seed_hook` replaces the single call to the seed
# wrapper at game+B2BD9; the rest is its state and the post-seed fingerprint.
SEED_LABELS = [
    "seed_hook", "seed_hook_used", "seed_fp_loop",
    "SEED_ON", "SEL_SEED", "SEED_USED", "SEED_FP",
    "PRB_SEEDN", "PRB_SEEDON", "PRB_SEEDVAL",
]

OVERLAY_LABELS += HOOK_LABELS
OVERLAY_LABELS += SEED_LABELS

sub(
    "overlay",
    "define(KEY_SHIFT,KEYS+18)\n",
    "define(KEY_SHIFT,KEYS+18)\n"
    "// --- F12 overlay (v0.4.0) ---\n"
    "define(KBD_IAT,game+3AC2E8)\n"       # GetKeyboardState, VA 0x7AC2E8
    "define(KEYSHADOW,game+5E0B8C)\n"     # game's DIK-indexed key array, VA 0x9E0B8C
    "define(box,game+D1010)\n",           # 6-arg rect, cdecl
    "the overlay's game addresses",
)

# v0.6.0: hint files.  The game already imports every API we need, so no import
# table surgery -- these are just IAT slots (all VAs = image base + RVA).
sub(
    "hint",
    "define(box,game+D1010)\n",
    "define(box,game+D1010)\n"
    "// --- hint file I/O (v0.6.0), all stdcall ---\n"
    "define(MODULE_IAT,game+3AC1B0)\n"    # GetModuleFileNameW, VA 0x7AC1B0
    "define(FILE_IAT,game+3AC238)\n"      # CreateFileW,         VA 0x7AC238
    "define(READ_IAT,game+3AC0E8)\n"      # ReadFile,            VA 0x7AC0E8
    "define(CLOSE_IAT,game+3AC250)\n"     # CloseHandle,         VA 0x7AC250
    "define(WRITE_IAT,game+3AC22C)\n"     # WriteFile,           VA 0x7AC22C
    "define(GETSIZE_IAT,game+3AC0E0)\n"   # GetFileSize,         VA 0x7AC0E0
    "define(SEEK_IAT,game+3AC0CC)\n"     # SetFilePointer,      VA 0x7AC0CC
    "define(FINDFIRST_IAT,game+3AC0D8)\n" # FindFirstFileW,      VA 0x7AC0D8
    "define(FINDNEXT_IAT,game+3AC0DC)\n"  # FindNextFileW,       VA 0x7AC0DC
    "define(FINDCLOSE_IAT,game+3AC0D4)\n",  # FindClose,         VA 0x7AC0D4
    "the hint file I/O imports",
)

sub(
    "overlay",
    "label(cave_end)\n",
    "".join("label(%s)\n" % n for n in OVERLAY_LABELS) + "label(cave_end)\n",
    "declare the overlay labels",
)

sub(
    "overlay",
    "[ENABLE]\n",
    "[ENABLE]\n"
    "// --- F12 overlay (v0.4.0): hooks inside the real per-frame function ---\n"
    "// game+CFFCD is 10 bytes into the frame function (mov [game+65110],1).\n"
    "assert(game+CFFCD,C7 05 10 51 A6 00 01 00 00 00)\n"
    "// game+14BD50 is the present function's entry: `push ebp / mov ebp,esp /\n"
    "// sub esp,0x4cc`.  It is called once per frame from game+DF9AF, at the\n"
    "// moment the scene has been drawn but nothing has been blitted yet, and\n"
    "// it is reached in every mode (title, menu, stage, replay).  That makes\n"
    "// it the one point where an overlay can be drawn and still be presented.\n"
    "assert(game+14BD50,55 8B EC 81 EC CC 04 00 00)\n"
    "// the four keyboard-refresh call sites, all `call game+140CD0`.\n"
    "assert(game+CF255,E8 76 1A 07 00)\n"
    "assert(game+CF2B5,E8 16 1A 07 00)\n"
    "assert(game+CF445,E8 86 18 07 00)\n"
    "assert(game+CF7CD,E8 FE 14 07 00)\n"
    "// The IAT slots hold the RVA of the hint/name entry on disk, which is\n"
    "// what pins us to this exact build.\n"
    "assert(game+3AC2E8,80 67 44 00)\n"
    "assert(game+3AC018,C4 68 44 00)\n"
    "assert(game+3AC01C,D8 68 44 00)\n"
    "assert(game+5E0B8C,00 00 00 00)\n"
    "// ---- v0.4.0: the game-over decision and the per-frame power clamp ----\n"
    "// game+B980C is the `cmp [player+0x48], 0 / jg <respawn>` that decides\n"
    "// between respawning and GAME OVER.  Six bytes, and the check happens\n"
    "// BEFORE the shared `dec [player+0x48]`, so \"pretend life == 1\" is enough.\n"
    "assert(game+B980C,83 78 48 00 7F 2E)\n"
    "// game+B9B05 is the tail of the player update: `clamp power into [0,500]`.\n"
    "// It runs every frame anyway, which is why freezing power here costs\n"
    "// nothing extra -- we are replacing an existing write, not adding one.\n"
    "assert(game+B9B05,8B 07 83 78 7C 00 7D 07 C7 40 7C 00 00 00 00 8B 07 81 78 7C F4 01 00 00 7C 07 C7 40 7C F4 01 00 00)\n"
    "// ---- v0.5.0: the RNG seed ----\n"
    "// game+B2BD9 is the ONLY call to the seed wrapper (verified by a full\n"
    "// .text sweep: the wrapper at 0xD04D0 has exactly one caller, and the\n"
    "// seed global 0xEDDFF4 has exactly one reader -- this one).  Five bytes.\n"
    "assert(game+B2BD9,E8 F2 D8 01 00)\n",
    "pin the overlay's hook sites",
)

OVERLAY_CODE = (
    "// =================================================================== //\n"
    "// F12 overlay (v0.4.0) -- infrastructure.                            //\n"
    "//   game+CFFCD  -> logic (read keys, menu)                            //\n"
    "//   game+CF7CD + 3 siblings -> run the game's input refresh, then     //\n"
    "//                  wipe KEYSHADOW while the menu is open              //\n"
    "//   game+14BD50 -> present-function entry: paint the overlay there    //\n"
    "// =================================================================== //\n"
    "overlay_entry:\n"
    "  pushfd\n"
    "  pushad\n"
    "  inc dword ptr [PRB_FRAMES]\n"
    "  call overlay_logic\n"
    "  popad\n"
    "  popfd\n"
    "  // re-execute the instruction we displaced, then rejoin the function\n"
    "  mov dword ptr [game+665110], 1\n"        # the original `mov [0xA65110],1`
    "  jmp game+CFFD7\n"
    "\n"
    "// ---- end-of-scene hook --------------------------------------------- //\n"
    "// game+14BD50 is the present function.  Its entry is the last point at\n"
    "// which the game's own drawing helpers still work AND nothing has been\n"
    "// blitted to the window yet, so the overlay we paint here is guaranteed\n"
    "// to be part of the frame the game is about to show.  (Drawing at the\n"
    "// end of the frame function instead is silently discarded: the renderer\n"
    "// is already torn down by then, which is why v0.3.1/v0.3.2 showed\n"
    "// nothing even though every hook fired.)\n"
    "overlay_present:\n"
    "  pushfd\n"
    "  pushad\n"
    "  inc dword ptr [PRB_PRES]\n"
    "  // v0.6.0: call this every frame, not only when the menu is open -- hint\n"
    "  // markers are meant to be visible while you are playing.  overlay_draw\n"
    "  // decides what actually gets painted.\n"
    "  call overlay_draw\n"
    "ovl_pres_done:\n"
    "  popad\n"
    "  popfd\n"
    "  // re-execute the prologue we displaced, then rejoin the function\n"
    "  push ebp\n"
    "  mov ebp, esp\n"
    "  sub esp, 4cc\n"
    "  jmp game+14BD59\n"
    "\n"
    "// ---- input-refresh wrapper ---------------------------------------- //\n"
    "// Entered by a `call` that replaced `call game+140CD0`, so the stack\n"
    "// is [ret][arg] -- exactly what the real callee expects.  All four\n"
    "// sites push one argument and `add esp,4` after the call.\n"
    "overlay_input:\n"
    "  pushfd\n"
    "  pushad\n"
    "  inc dword ptr [PRB_INPUT]\n"
    "  push dword ptr [esp+40]\n"
    "  call game+140CD0\n"
    "  add esp, 4\n"
    "  cmp dword ptr [OVERLAY_OPEN], 0\n"
    "  je ovl_in_done\n"
    "  xor eax, eax\n"
    "  mov ecx, 40\n"
    "  mov edi, KEYSHADOW\n"
    "ovl_in_clear:\n"
    "  mov [edi], eax\n"
    "  add edi, 4\n"
    "  dec ecx\n"
    "  jnz ovl_in_clear\n"
    "ovl_in_done:\n"
    "  popad\n"
    "  popfd\n"
    "  ret\n"
    "\n"
    "overlay_logic:\n"
    "  pushfd\n"
    "  pushad\n"
    "  // A new frame starts here: allow exactly one overlay draw this frame.\n"
    "  mov dword ptr [OVL_DRAWN], 0\n"
    "  // ---- settings file (v0.7.8): load once, then persist any change ----\n"
    "  // Deliberately first, and before the menu-open test further down: it\n"
    "  // must run in every scene, not only while the F12 panel is up.\n"
    "  call cfg_tick\n"
    "  // Mirror the hit counter into its read-only menu row.  It counts every\n"
    "  // hit, not just fatal ones -- see NOSORE_DEBT.\n"
    "  mov eax, [NOSORE_DEBT]\n"
    "  mov [OVL_V_DEBT], eax\n"
    "  // Same for the stage frame counter at [stage+0x4C].  The pointer is only\n"
    "  // stashed at stage start, so range-check it: outside the stage it holds a\n"
    "  // stale value, and a wild pointer here would fault on every frame.\n"
    "  mov eax, [DBG_STAGE]\n"
    "  cmp eax, 10000\n"
    "  jb ovl_frame_done\n"
    "  cmp eax, 7FFF0000\n"
    "  ja ovl_frame_done\n"
    "  mov eax, [eax+4C]\n"
    "ovl_frame_done:\n"
    "  mov [OVL_V_FRAME], eax\n"
    "  // ---- boss pattern tracking (v0.7.2) --------------------------------\n"
    "  // MUST live up here, not down with the menu work: when the menu is\n"
    "  // closed overlay_logic jumps straight to ovl_logic_done, so anything\n"
    "  // after that point only runs while F12 is open -- and the boss patterns\n"
    "  // have to be tracked during ordinary play.\n"
    "  //\n"
    "  // POLL, do not hook: the pattern index is reachable from the stage object\n"
    "  // we already keep, and the one obvious hook site (game+27E90) is already\n"
    "  // taken by BAN's applyPatternIdWarp.  The chain, all verified against the\n"
    "  // vanilla exe:\n"
    "  //   RVA 0xB2F4C  mov [stage+8], eax    ; the boss manager\n"
    "  //   RVA 0x27E90  mov [manager+0], eax  ; the boss pattern object\n"
    "  //   ...and the game keeps the 0-BASED pattern ordinal at [boss+0x44]\n"
    "  //      (0 = the first pattern of the stage = the mid non-spell).\n"
    "  // See the long evidence chain further down, right before the read -- it\n"
    "  // covers the doc quote, BAN's own write site, and the live F12 read.\n"
    "  //\n"
    "  // [stage+0x30] (the stage number, 1..7) doubles as a liveness check, so a\n"
    "  // stale DBG_STAGE -- between stages, or on the title screen -- can never\n"
    "  // make us walk into freed memory.\n"
    "  mov eax, [DBG_STAGE]\n"
    "  cmp eax, 10000\n"
    "  jb ovl_boss_clear\n"
    "  cmp eax, 7FFF0000\n"
    "  ja ovl_boss_clear\n"
    "  mov ecx, [eax+30]\n"
    "  cmp ecx, 1\n"
    "  jb ovl_boss_clear\n"
    "  cmp ecx, 7\n"
    "  ja ovl_boss_clear\n"
    "  mov eax, [eax+8]\n"
    "  cmp eax, 10000\n"
    "  jb ovl_boss_clear\n"
    "  cmp eax, 7FFF0000\n"
    "  ja ovl_boss_clear\n"
    "  mov eax, [eax]\n"
    "  cmp eax, 10000\n"
    "  jb ovl_boss_clear\n"
    "  cmp eax, 7FFF0000\n"
    "  ja ovl_boss_clear\n"
    "  // ---- is a boss/mid-boss on screen at all? ----\n"
    "  // [boss+0x08] is the gate, NOT [boss+0x44].  Measured through stage 1:\n"
    "  //   0x08: 0 mid-stage, 1 from frame 2600 (mid-boss) to 2805, 0 until\n"
    "  //         4000, then 1 again for the stage boss.\n"
    "  //\n"
    "  // [boss+0x44] is the game's own \"Pattern number\" -- and it is 0-BASED.\n"
    "  //\n"
    "  // v0.7.6 -- this was wrong twice, so here is the evidence chain.\n"
    "  //\n"
    "  // (1) The authoritative practice doc for this game\n"
    "  //     (D:/STG/leprac/EMSRMIprac.txt) says, of the value you warp with:\n"
    "  //       \"This value determines what pattern the boss will use.  The\n"
    "  //        FIRST pattern of the stage will have a value of 0, the second\n"
    "  //        will have 1, third 2 etc.\"\n"
    "  //\n"
    "  // (2) BAN's own upstream source writes exactly that value here.  Its\n"
    "  //     applyPatternIdWarp hook (game+27E90) does\n"
    "  //         mov ebx, [SELECTED_ID]\n"
    "  //         mov [eax+44], ebx\n"
    "  //     and SELECTED_ID is built as\n"
    "  //         mov ebx, [IDS_TABLE+eax*4]     ; ids_0 = FFFFFFFF 0 1 2 3 4 5\n"
    "  //         mov edx, [ebx+ecx*4]           ; ecx = menu row index\n"
    "  //     with the names_0 row list being\n"
    "  //         None / MNon 1 / MSpell 1 / Non 1 / Spell 1 / Non 2 / Spell 2\n"
    "  //\n"
    "  // (3) The F12 menu of the PREVIOUS build settled it.  During stage 1 the\n"
    "  //     user read: mid non -> -1, mid spell -> 0.  That build displayed\n"
    "  //     `raw - 1`, so mid non really has raw 0 and mid spell raw 1.\n"
    "  //\n"
    "  // (4) This build's own probe agrees: [boss+0x44] becomes 0 on the exact\n"
    "  //     frame the mid-boss appears (stage frame 2600).\n"
    "  //\n"
    "  // So the ordinal to expose is [boss+0x44] ITSELF -- value 0 is the mid\n"
    "  // non-spell, which is exactly what the hint file's `boss:0:...` must\n"
    "  // match.  (v0.7.4 subtracted 1 and so shifted every window up by one\n"
    "  // pattern, which is why `boss:0:0 -> boss:1:0` lit up during the mid\n"
    "  // SPELL instead of the mid non.)\n"
    "  mov ecx, [eax+8]\n"
    "  test ecx, ecx\n"
    "  jz ovl_boss_clear\n"
    "  // ---- a new fight just began? ----\n"
    "  // A freshly built boss object carries the PREVIOUS fight's last pattern\n"
    "  // number until its own first pattern starts.  Left alone that shows the\n"
    "  // mid-boss's last spell for the whole of the stage boss's intro dialogue.\n"
    "  // Patterns only ever increase, so the first pattern of a new fight can\n"
    "  // never legitimately equal the last one of the previous fight -- which\n"
    "  // makes that value safe to treat as \"not started yet\" and skip.\n"
    "  cmp dword ptr [HINT_PAT_WAS], 0\n"
    "  jne ovl_boss_same_fight\n"
    "  mov ecx, [HINT_PAT_LAST]\n"
    "  mov [HINT_PAT_SKIP], ecx\n"
    "ovl_boss_same_fight:\n"
    "  mov dword ptr [HINT_PAT_WAS], 1\n"
    "  mov eax, [eax+44]\n"
    "  // v0.7.5 -- sanity-clamp the raw ordinal, and reject negatives.\n"
    "  //\n"
    "  // The pointer chain above can only prove the address is PLAUSIBLE, not\n"
    "  // that the object is still alive: during boss teardown the manager still\n"
    "  // points at memory the game has already recycled, and one frame of a\n"
    "  // real stage-1 run was measured reading [boss+0x44] = 0xCC8A9D04 (heap\n"
    "  // fill junk) and [boss+0x08] = 0x1F6E0A6A (junk that happens to be\n"
    "  // non-zero, so the on-screen gate passed it).  Left unchecked that\n"
    "  // garbage got stored in HINT_PAT_IDX / HINT_PAT_LAST and could suppress\n"
    "  // a legitimate pattern in the NEXT fight via HINT_PAT_SKIP.\n"
    "  //\n"
    "  // No stage of this game has anywhere near 0x400 patterns\n"
    "  // (MAX_PATTERNID tops out at 0x15), so anything outside 0..0x3FF is junk\n"
    "  // and is treated as \"not on a pattern\" (HINT_PAT_ON = 0), i.e. the same\n"
    "  // state as mid-stage.  Signed compare so a negative raw lands there too.\n"
    "  cmp eax, 0\n"
    "  jl ovl_boss_zero\n"
    "  cmp eax, 400\n"
    "  jae ovl_boss_zero\n"
    "  jmp ovl_boss_have\n"
    "ovl_boss_zero:\n"
    "  // v0.7.6 -- this label now means \"the boss is on screen but we cannot\n"
    "  // trust a pattern number for it\": either the raw field is garbage\n"
    "  // (out of 0..0x3FF) or negative.  A boss IS present, we just do not know\n"
    "  // which pattern, so leave HINT_PAT_IDX at its last known value and keep\n"
    "  // HINT_PAT_ON = 0 so no boss:P:F window can fire.\n"
    "  //\n"
    "  // NOTE: raw 0 is NOT routed here any more -- 0 is the mid non-spell\n"
    "  // (see the evidence chain above), so it takes the normal ovl_boss_have\n"
    "  // path and HINT_PAT_IDX becomes 0.\n"
    "  mov dword ptr [HINT_PAT_ON], 0\n"
    "  jmp ovl_boss_done\n"
    "ovl_boss_have:\n"
    "  cmp eax, [HINT_PAT_SKIP]\n"
    "  je ovl_boss_suppress\n"
    "  mov dword ptr [HINT_PAT_SKIP], FFFFFFFF\n"
    "  cmp eax, [HINT_PAT_IDX]\n"
    "  je ovl_boss_tick\n"
    "  // A new pattern: restart the pattern-local clock.\n"
    "  mov [HINT_PAT_IDX], eax\n"
    "  mov [HINT_PAT_LAST], eax\n"
    "  mov dword ptr [HINT_PAT_FRAME], 0\n"
    "  mov dword ptr [HINT_PAT_ON], 1\n"
    "  jmp ovl_boss_done\n"
    "ovl_boss_tick:\n"
    "  // The pattern-local frame count is OUR OWN counter, incremented once per\n"
    "  // frame, and NOT a delta on [stage+0x4C].  That stage timer FREEZES for\n"
    "  // the duration of the intro dialogue (measured: 13 frames over 55 seconds\n"
    "  // across the mid non-spell), so a delta on it would sit near zero for the\n"
    "  // whole first pattern of a fight and boss:P:F could never fire.\n"
    "  inc dword ptr [HINT_PAT_FRAME]\n"
    "  mov dword ptr [HINT_PAT_ON], 1\n"
    "  jmp ovl_boss_done\n"
    "ovl_boss_suppress:\n"
    "  mov dword ptr [HINT_PAT_ON], 0\n"
    "  jmp ovl_boss_done\n"
    "ovl_boss_clear:\n"
    "  mov dword ptr [HINT_PAT_ON], 0\n"
    "  mov dword ptr [HINT_PAT_WAS], 0\n"
    "  mov dword ptr [HINT_PAT_IDX], 0\n"
    "ovl_boss_done:\n"
    "  // Mirror into the read-only Pattern row.  Deliberately a mirror of\n"
    "  // HINT_PAT_IDX and not a second read of the game: the row must show what\n"
    "  // the hint logic is actually using, or it is useless for working out\n"
    "  // which number to write in a boss:P:F window.\n"
    "  //\n"
    "  // Mid-stage it shows -1, NOT 0.  Pattern 0 is a real pattern (the mid\n"
    "  // non-spell), so \"no boss\" has to be a different value or the two are\n"
    "  // indistinguishable -- exactly the trap that made a boss:0 window light\n"
    "  // up in the middle of the mid-stage.\n"
    "  mov eax, [HINT_PAT_IDX]\n"
    "  cmp dword ptr [HINT_PAT_ON], 0\n"
    "  jne ovl_boss_mirror\n"
    "  mov eax, FFFFFFFF\n"
    "ovl_boss_mirror:\n"
    "  mov [OVL_V_PATTERN], eax\n"
    "  // ---- the physical keyboard, into our own 256-byte buffer ----\n"
    "  push OVL_VKBUF\n"
    "  call dword ptr [KBD_IAT]\n"
    "  movzx eax, byte ptr [OVL_VKBUF+7B]\n"
    "  mov [PRB_F12], eax\n"
    "  // ---- F12 (VK 7B) rising edge toggles the menu ----\n"
    "  and al, 80\n"
    "  mov cl, byte ptr [OVL_PREV_F12]\n"
    "  mov byte ptr [OVL_PREV_F12], al\n"
    "  cmp al, cl\n"
    "  je ovl_toggle_done\n"
    "  test al, al\n"
    "  jz ovl_toggle_done\n"
    "  xor dword ptr [OVERLAY_OPEN], 1\n"
    "  inc dword ptr [PRB_F12N]\n"
    "ovl_toggle_done:\n"
    "  mov eax, [OVERLAY_OPEN]\n"
    "  mov [PRB_OPEN], eax\n"
    "  // NOTE: the old \"freeze while the menu is open\" switch lived here.  It\n"
    "  // was never verified (see plan-hint.md 19) and the user asked for it to\n"
    "  // be dropped, so the row and this branch are both gone.\n"
    "  cmp eax, 0\n"
    "  jne ovl_menu_open\n"
    "  // Closed: forget the edges and the held key so reopening starts clean,\n"
    "  // and make sure the Seed row is showing its normal label again.\n"
    "  mov dword ptr [OVL_PREV_KEYS], 0\n"
    "  mov dword ptr [OVL_PREV_KEYS+4], 0\n"
    "  call ovl_type_exit\n"
    "  call ovl_reset_hold\n"
    "  jmp ovl_logic_done\n"
    "ovl_menu_open:\n"
    "  mov al, byte ptr [OVL_VKBUF+26]\n"      # UP
    "  and al, 80\n"
    "  mov cl, byte ptr [OVL_PREV_KEYS+0]\n"
    "  mov byte ptr [OVL_PREV_KEYS+0], al\n"
    "  cmp al, cl\n"
    "  je ovl_up_done\n"
    "  test al, al\n"
    "  jz ovl_up_done\n"
    "  call ovl_move_up\n"
    "ovl_up_done:\n"
    "  mov al, byte ptr [OVL_VKBUF+28]\n"      # DOWN
    "  and al, 80\n"
    "  mov cl, byte ptr [OVL_PREV_KEYS+1]\n"
    "  mov byte ptr [OVL_PREV_KEYS+1], al\n"
    "  cmp al, cl\n"
    "  je ovl_down_done\n"
    "  test al, al\n"
    "  jz ovl_down_done\n"
    "  call ovl_move_down\n"
    "ovl_down_done:\n"
    "  mov al, byte ptr [OVL_VKBUF+25]\n"      # LEFT
    "  and al, 80\n"
    "  mov cl, byte ptr [OVL_PREV_KEYS+2]\n"
    "  mov byte ptr [OVL_PREV_KEYS+2], al\n"
    "  cmp al, cl\n"
    "  je ovl_left_done\n"
    "  test al, al\n"
    "  jz ovl_left_done\n"
    "  call ovl_move_left\n"
    "ovl_left_done:\n"
    "  mov al, byte ptr [OVL_VKBUF+27]\n"      # RIGHT
    "  and al, 80\n"
    "  mov cl, byte ptr [OVL_PREV_KEYS+3]\n"
    "  mov byte ptr [OVL_PREV_KEYS+3], al\n"
    "  cmp al, cl\n"
    "  je ovl_right_done\n"
    "  test al, al\n"
    "  jz ovl_right_done\n"
    "  call ovl_move_right\n"
    "ovl_right_done:\n"
    "  // ---- held LEFT/RIGHT: after OVL_HOLD_DELAY frames, fine-step by 1 --\n"
    "  mov dl, byte ptr [OVL_VKBUF+27]\n"      # RIGHT
    "  and dl, 80\n"
    "  jz ovl_hold_not_right\n"
    "  mov ecx, 1\n"
    "  jmp ovl_hold_check\n"
    "ovl_hold_not_right:\n"
    "  mov dl, byte ptr [OVL_VKBUF+25]\n"      # LEFT
    "  and dl, 80\n"
    "  jz ovl_hold_none\n"
    "  mov ecx, 2\n"
    "ovl_hold_check:\n"
    "  cmp ecx, [OVL_HOLD_DIR]\n"
    "  jne ovl_hold_new\n"
    "  inc dword ptr [OVL_HOLD_N]\n"
    "  mov eax, [OVL_HOLD_N]\n"
    "  cmp eax, [OVL_HOLD_DELAY]\n"
    "  jl ovl_hold_done\n"
    "  inc dword ptr [OVL_NUDGE_N]\n"
    "  mov eax, [OVL_NUDGE_N]\n"
    "  cmp eax, [OVL_NUDGE_EVERY]\n"
    "  jl ovl_hold_done\n"
    "  mov dword ptr [OVL_NUDGE_N], 0\n"
    "  cmp ecx, 1\n"
    "  jne ovl_hold_left\n"
    "  call ovl_nudge_right\n"
    "  jmp ovl_hold_done\n"
    "ovl_hold_left:\n"
    "  call ovl_nudge_left\n"
    "  jmp ovl_hold_done\n"
    "ovl_hold_new:\n"
    "  mov [OVL_HOLD_DIR], ecx\n"
    "  mov dword ptr [OVL_HOLD_N], 0\n"
    "  mov dword ptr [OVL_NUDGE_N], 0\n"
    "  jmp ovl_hold_done\n"
    "ovl_hold_none:\n"
    "  call ovl_reset_hold\n"
    "ovl_hold_done:\n"
    "  // ---- Lock Seed rising edge: adopt the seed already in use ----------\n"
    "  // Deliberately SEED_USED (what the RNG was actually seeded with at this\n"
    "  // stage's start) and NOT the seed global at 0xEDDFF4.  Measured: the\n"
    "  // global is stable during play but does NOT hold the seed the RNG got --\n"
    "  // a second code path (0x72E39) overwrites it with a bare A*A right after\n"
    "  // the stage scene is built.  SEED_USED is the value handed to the seed\n"
    "  // wrapper, which is the thing a replay has to reproduce.\n"
    "  mov eax, [SEED_ON]\n"
    "  cmp eax, [OVL_PREV_SEEDSW]\n"
    "  je ovl_seedsw_done\n"
    "  mov [OVL_PREV_SEEDSW], eax\n"
    "  test eax, eax\n"
    "  jz ovl_seedsw_done\n"
    "  mov eax, [SEED_USED]\n"
    "  mov [SEL_SEED], eax\n"
    "ovl_seedsw_done:\n"
    "  // Capture is triggered by Z on its row (see ovl_type_toggle), so its\n"
    "  // value is read-only and just shows how many lines have been written.\n"
    "  // ---- the Seed row's direct digit entry ----\n"
    "  call ovl_type_keys\n"
    "  // ---- suppress the game's own keyboard input while the menu is open --\n"
    "  // The game rebuilds KEYSHADOW from GetKeyboardState earlier in the\n"
    "  // frame, so clearing it here means gameplay sees nothing pressed.\n"
    "  xor eax, eax\n"
    "  mov ecx, 40\n"                            # 0x40 dwords = 0x100 bytes
    "  mov edi, KEYSHADOW\n"
    "ovl_clear:\n"
    "  mov [edi], eax\n"
    "  add edi, 4\n"
    "  dec ecx\n"
    "  jnz ovl_clear\n"
    "ovl_logic_done:\n"
    "  popad\n"
    "  popfd\n"
    "  ret\n"
    "\n"
    "ovl_move_up:\n"
    "  mov eax, [OVL_CUR]\n"
    "  dec eax\n"
    "  jns ovl_up_ok\n"
    "  mov eax, [OVL_ROWS_N]\n"
    "  dec eax\n"
    "ovl_up_ok:\n"
    "  mov [OVL_CUR], eax\n"
    "  ret\n"
    "\n"
    "ovl_move_down:\n"
    "  mov eax, [OVL_CUR]\n"
    "  inc eax\n"
    "  cmp eax, [OVL_ROWS_N]\n"
    "  jl ovl_down_ok\n"
    "  xor eax, eax\n"
    "ovl_down_ok:\n"
    "  mov [OVL_CUR], eax\n"
    "  ret\n"
    "\n"
    "// A row is six dwords: text, value pointer, min, max, step, wrap.\n"
    "// `wrap` = 1 -> stepping past an end jumps to the other end (a switch);\n"
    "//          0 -> stepping past an end stops there (a wide range, so the\n"
    "//               held-key nudge below can land on an exact value).\n"
    "//\n"
    "// ovl_row: esi = &OVL_ROWS[OVL_CUR]\n"
    "ovl_row:\n"
    "  mov esi, [OVL_CUR]\n"
    "  imul esi, esi, 18\n"
    "  add esi, OVL_ROWS\n"
    "  ret\n"
    "\n"
    "// ovl_apply: esi = row pointer, edx = signed delta.\n"
    "// The range checks are UNSIGNED: the Seed row's max is FFFFFFFF, which as a\n"
    "// signed value is -1, so a signed compare would make RIGHT clamp to\n"
    "// FFFFFFFF from anywhere.  Every other row has max <= 65535, where signed\n"
    "// and unsigned agree, so this is a strict widening.\n"
    "ovl_apply:\n"
    "  mov eax, [esi+4]\n"
    "  mov ecx, [eax]\n"
    "  add ecx, edx\n"
    "  cmp ecx, [esi+0C]\n"
    "  jbe ovl_apply_lo\n"
    "  cmp dword ptr [esi+14], 0\n"
    "  je ovl_apply_hi_clamp\n"
    "  mov ecx, [esi+8]\n"
    "  jmp ovl_apply_store\n"
    "ovl_apply_hi_clamp:\n"
    "  mov ecx, [esi+0C]\n"
    "  jmp ovl_apply_store\n"
    "ovl_apply_lo:\n"
    "  cmp ecx, [esi+8]\n"
    "  jae ovl_apply_store\n"
    "  cmp dword ptr [esi+14], 0\n"
    "  je ovl_apply_lo_clamp\n"
    "  mov ecx, [esi+0C]\n"
    "  jmp ovl_apply_store\n"
    "ovl_apply_lo_clamp:\n"
    "  mov ecx, [esi+8]\n"
    "ovl_apply_store:\n"
    "  mov [eax], ecx\n"
    "  ret\n"
    "\n"
    "// While the seed row is in typing mode the arrow keys must not fight the\n"
    "// digits, so all four value-movers bail out through one shared exit.\n"
    "ovl_move_right:\n"
    "  cmp dword ptr [OVL_TYPE_ON], 0\n"
    "  jne ovl_move_blocked\n"
    "  call ovl_row\n"
    "  mov edx, [esi+10]\n"
    "  jmp ovl_apply\n"
    "\n"
    "ovl_move_left:\n"
    "  cmp dword ptr [OVL_TYPE_ON], 0\n"
    "  jne ovl_move_blocked\n"
    "  call ovl_row\n"
    "  mov edx, [esi+10]\n"
    "  neg edx\n"
    "  jmp ovl_apply\n"
    "\n"
    "ovl_nudge_right:\n"
    "  cmp dword ptr [OVL_TYPE_ON], 0\n"
    "  jne ovl_move_blocked\n"
    "  call ovl_row\n"
    "  mov edx, 1\n"
    "  jmp ovl_apply\n"
    "\n"
    "ovl_nudge_left:\n"
    "  cmp dword ptr [OVL_TYPE_ON], 0\n"
    "  jne ovl_move_blocked\n"
    "  call ovl_row\n"
    "  mov edx, ffffffff\n"
    "  jmp ovl_apply\n"
    "\n"
    "ovl_move_blocked:\n"
    "  ret\n"
    "\n"
    "ovl_reset_hold:\n"
    "  mov dword ptr [OVL_HOLD_DIR], 0\n"
    "  mov dword ptr [OVL_HOLD_N], 0\n"
    "  mov dword ptr [OVL_NUDGE_N], 0\n"
    "  ret\n"
    "\n"
    "// ================= seed row: direct digit entry ===================== //\n"
    "// The overlay already reads GetKeyboardState into OVL_VKBUF, so digits are\n"
    "// just VK 30..39.  Typing beats nudging for a 32-bit value: 4294967295 is\n"
    "// ten digits, and no step size makes that pleasant.\n"
    "//\n"
    "//   Z        enter typing (cursor on the Seed row) / commit\n"
    "//   digits   append; the FIRST digit replaces the old value\n"
    "//   BACK(08) drop the last digit\n"
    "//   ESC      cancel, restore the value you started with\n"
    "//\n"
    "// Edge detection for all ten digits with one state word: remember the VK of\n"
    "// the digit currently held, and only act when a *different* one goes down.\n"
    "// That also handles rolling from 5 to 6 without releasing 5.\n"
    "ovl_type_keys:\n"
    "  // ---- Z (5A) ----\n"
    "  mov al, byte ptr [OVL_VKBUF+5A]\n"
    "  and al, 80\n"
    "  mov cl, byte ptr [OVL_PREV_KEYS+4]\n"
    "  mov byte ptr [OVL_PREV_KEYS+4], al\n"
    "  cmp al, cl\n"
    "  je ovl_type_z_done\n"
    "  test al, al\n"
    "  jz ovl_type_z_done\n"
    "  call ovl_type_toggle\n"
    "ovl_type_z_done:\n"
    "  // ---- ESC (1B) ----\n"
    "  mov al, byte ptr [OVL_VKBUF+1B]\n"
    "  and al, 80\n"
    "  mov cl, byte ptr [OVL_PREV_KEYS+5]\n"
    "  mov byte ptr [OVL_PREV_KEYS+5], al\n"
    "  cmp al, cl\n"
    "  je ovl_type_esc_done\n"
    "  test al, al\n"
    "  jz ovl_type_esc_done\n"
    "  call ovl_type_cancel\n"
    "ovl_type_esc_done:\n"
    "  // ---- BACK (08) ----\n"
    "  mov al, byte ptr [OVL_VKBUF+08]\n"
    "  and al, 80\n"
    "  mov cl, byte ptr [OVL_PREV_KEYS+6]\n"
    "  mov byte ptr [OVL_PREV_KEYS+6], al\n"
    "  cmp al, cl\n"
    "  je ovl_type_back_done\n"
    "  test al, al\n"
    "  jz ovl_type_back_done\n"
    "  cmp dword ptr [OVL_TYPE_ON], 0\n"
    "  je ovl_type_back_done\n"
    "  mov eax, [SEL_SEED]\n"
    "  xor edx, edx\n"
    "  mov ecx, 0A\n"
    "  div ecx\n"
    "  mov [SEL_SEED], eax\n"
    "ovl_type_back_done:\n"
    "  // ---- digits ----\n"
    "  cmp dword ptr [OVL_TYPE_ON], 0\n"
    "  je ovl_type_digits_done\n"
    "  // ebx tracks whether ANY digit is currently down.  Only when none is\n"
    "  // down may OVL_TYPE_LAST be cleared -- clearing it at the end of the\n"
    "  // scan while a key is still held makes the very next call see a fresh\n"
    "  // press, which doubles every digit (the overlay runs twice per frame).\n"
    "  xor ebx, ebx\n"
    "  mov ecx, 30\n"
    "ovl_type_digit_loop:\n"
    "  movzx eax, byte ptr [OVL_VKBUF+ecx]\n"
    "  and al, 80\n"
    "  jz ovl_type_digit_next\n"
    "  mov ebx, 1\n"
    "  cmp ecx, [OVL_TYPE_LAST]\n"
    "  je ovl_type_digit_next\n"
    "  mov [OVL_TYPE_LAST], ecx\n"
    "  mov edx, ecx\n"
    "  sub edx, 30\n"
    "  call ovl_type_append\n"
    "  jmp ovl_type_digits_done\n"
    "ovl_type_digit_next:\n"
    "  inc ecx\n"
    "  cmp ecx, 3A\n"
    "  jl ovl_type_digit_loop\n"
    "  test ebx, ebx\n"
    "  jnz ovl_type_digits_done\n"
    "  mov dword ptr [OVL_TYPE_LAST], 0\n"
    "ovl_type_digits_done:\n"
    "  ret\n"
    "\n"
    "// Z.  Which row the cursor is on decides what it does:\n"
    "//   any 0..1 row   -> flip it (these render as on/off)\n"
    "//   the Seed row   -> enter/commit direct digit entry\n"
    "//   the Capture row-> capture the current spot once\n"
    "// EVERY case is decided from the row DESCRIPTOR -- its value pointer, or\n"
    "// its min/max range -- and never from a row INDEX.  Hard-coded indices are\n"
    "// exactly what once made the Capture row render the Seed label and steal\n"
    "// its digit entry, the moment the hint rows were inserted above the seed\n"
    "// rows.  With this form, reordering the table cannot break the dispatch.\n"
    "ovl_type_toggle:\n"
    "  cmp dword ptr [OVL_TYPE_ON], 0\n"
    "  jne ovl_type_commit\n"
    "  call ovl_row\n"                           # esi = &OVL_ROWS[OVL_CUR]
    "  cmp dword ptr [esi+0C], 1\n"              # max == 1 ?
    "  jne ovl_type_try_seed\n"
    "  cmp dword ptr [esi+8], 0\n"               # min == 0 ?
    "  jne ovl_type_try_seed\n"
    "  mov eax, [esi+4]\n"
    "  mov ecx, [eax]\n"
    "  xor ecx, 1\n"
    "  mov [eax], ecx\n"
    "  ret\n"
    "ovl_type_try_seed:\n"
    "  mov eax, SEL_SEED\n"                     # the Seed row's value pointer
    "  cmp [esi+4], eax\n"
    "  jne ovl_type_try_capture\n"
    "  mov eax, [SEL_SEED]\n"
    "  mov [OVL_TYPE_OLD], eax\n"
    "  mov dword ptr [OVL_TYPE_FRESH], 1\n"
    "  mov dword ptr [OVL_TYPE_LAST], 0\n"
    "  mov dword ptr [OVL_TYPE_ON], 1\n"
    "  // Remember WHICH row is in typing mode, so restoring its label later\n"
    "  // needs no row index either.\n"
    "  mov [OVL_TYPE_ROW], esi\n"
    "  mov eax, TXT_OVL_SEED_EDIT\n"
    "  mov [esi], eax\n"
    "  ret\n"
    "ovl_type_try_capture:\n"
    "  mov eax, OVL_V_CAPTURE\n"                # the Capture row's value pointer
    "  cmp [esi+4], eax\n"
    "  jne ovl_type_toggle_done\n"
    "  call hint_capture\n"
    "  cmp dword ptr [HINT_CAP_OK], 0\n"
    "  je ovl_type_toggle_done\n"
    "  inc dword ptr [OVL_V_CAPTURE]\n"         # the count is the feedback
    "  ret\n"
    "ovl_type_commit:\n"
    "  // Committing a hand-typed seed switches the lock on -- you typed it, so\n"
    "  // you want it used -- and arms the edge detector so the Lock Seed row\n"
    "  // does not immediately grab the current seed over the top of it.\n"
    "  // (To grab instead, toggle Lock Seed off and on again.)\n"
    "  mov dword ptr [SEED_ON], 1\n"
    "  mov dword ptr [OVL_PREV_SEEDSW], 1\n"
    "  jmp ovl_type_exit\n"
    "ovl_type_exit:\n"
    "  mov dword ptr [OVL_TYPE_ON], 0\n"
    "  mov dword ptr [OVL_TYPE_LAST], 0\n"
    "  mov ecx, [OVL_TYPE_ROW]\n"
    "  test ecx, ecx\n"
    "  jz ovl_type_toggle_done\n"                # typing was never entered
    "  mov eax, TXT_OVL_SEED\n"
    "  mov [ecx], eax\n"
    "ovl_type_toggle_done:\n"
    "  ret\n"
    "\n"
    "ovl_type_cancel:\n"
    "  cmp dword ptr [OVL_TYPE_ON], 0\n"
    "  je ovl_type_cancel_done\n"
    "  mov eax, [OVL_TYPE_OLD]\n"
    "  mov [SEL_SEED], eax\n"
    "  jmp ovl_type_exit\n"
    "ovl_type_cancel_done:\n"
    "  ret\n"
    "\n"
    "// edx = the digit (0..9).  Append to SEL_SEED, clamped at FFFFFFFF.\n"
    "// The first digit after entering typing mode replaces the value, so you do\n"
    "// not have to backspace away a previous seed before typing a new one.\n"
    "ovl_type_append:\n"
    "  cmp dword ptr [OVL_TYPE_FRESH], 0\n"
    "  je ovl_type_app_shift\n"
    "  mov dword ptr [OVL_TYPE_FRESH], 0\n"
    "  mov [SEL_SEED], edx\n"
    "  ret\n"
    "ovl_type_app_shift:\n"
    "  mov eax, [SEL_SEED]\n"
    "  cmp eax, 19999999\n"                    # 429496729: one more digit might not fit
    "  ja ovl_type_app_done\n"
    "  jne ovl_type_app_room\n"
    "  cmp edx, 5\n"                           # ...and 4294967295 is the ceiling
    "  ja ovl_type_app_done\n"
    "ovl_type_app_room:\n"
    "  imul eax, eax, 0A\n"
    "  add eax, edx\n"
    "  mov [SEL_SEED], eax\n"
    "ovl_type_app_done:\n"
    "  ret\n"
    "\n"
    "ovl_getColor:\n"
    "  // eax = row index; the selected row draws dark, the rest bright.\n"
    "  cmp eax, [OVL_CUR]\n"
    "  je ovl_color_sel\n"
    "  mov eax, FF\n"
    "  ret\n"
    "ovl_color_sel:\n"
    "  xor eax, eax\n"
    "  ret\n"
    "\n"
    "overlay_draw:\n"
    "  pushfd\n"
    "  pushad\n"
    "  inc dword ptr [PRB_BLIT]\n"
    "  // Draw once per frame at most: several blit sites may fire, and the\n"
    "  // overlay must not be painted N times on top of itself.\n"
    "  cmp dword ptr [OVL_DRAWN], 0\n"
    "  jne ovl_draw_done\n"
    "  mov dword ptr [OVL_DRAWN], 1\n"
    "  // ---- the self-machine cross first, so hint markers and the panel sit\n"
    "  //      on top of it.  Independent of the Hint switch (v0.7.7). ----\n"
    "  call draw_pcross\n"
    "  // ---- hint markers next, so the panel sits on top of them ----\n"
    "  cmp dword ptr [OVL_V_HINT], 0\n"
    "  je ovl_draw_panel\n"
    "  call draw_hints\n"
    "ovl_draw_panel:\n"
    "  cmp dword ptr [OVERLAY_OPEN], 0\n"
    "  je ovl_draw_done\n"
    "  // ---- the panel.  box(x1,y1,x2,y2,colour,filled) is cdecl with six\n"
    "  //      args; we pass both values of `filled` so we get the solid pass\n"
    "  //      whichever of the two inner primitives actually fills.\n"
    "  push 1\n"                                 # arg6 filled
    "  push 0\n"                                 # colour
    "  push E8\n"                                # y2 -- twelve rows (v0.7.7 added Player +)
    "  push F0\n"                                # x2 -- wide enough for a 10-digit seed
    "  push 10\n"                                # y1
    "  push 10\n"                                # x1
    "  call box\n"
    "  push 0\n"                                 # arg6 outline
    "  push ff\n"                                # colour
    "  push E8\n"
    "  push F0\n"
    "  push 10\n"
    "  push 10\n"
    "  call box\n"
    "  add esp, 30\n"                            # 12 dwords
    "  // ---- title: shadow at (19,19), then the real one at (18,18) ----\n"
    "  push 0\n"
    "  push TXT_OVL_TITLE\n"
    "  push 0\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  push 19\n"
    "  push 19\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  push 0\n"
    "  push TXT_OVL_TITLE\n"
    "  push ff\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  push 18\n"
    "  push 18\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  // ---- rows ----\n"
    "  // The row cursor lives in MEMORY and is reloaded every iteration.\n"
    "  // getTextTexture / drawTextTexture are game functions and this engine's\n"
    "  // drawing helpers do NOT preserve ecx/edx/esi (box() clobbers them too).\n"
    "  // Holding the cursor in a register across those calls is exactly what made\n"
    "  // one row render another row's label.\n"
    "  mov dword ptr [OVL_RCUR], 0\n"
    "ovl_draw_row:\n"
    "  mov eax, [OVL_RCUR]\n"
    "  cmp eax, [OVL_ROWS_N]\n"
    "  jge ovl_draw_done\n"
    "  imul eax, eax, 18\n"                       # six dwords per row
    "  add eax, OVL_ROWS\n"
    "  mov [OVL_RPTR], eax\n"
    "  mov eax, [OVL_RCUR]\n"
    "  imul eax, eax, 10\n"
    "  add eax, 28\n"
    "  mov [OVL_RY], eax\n"
    "  // ---- pick this row's label ----\n"
    "  // OVL_ALT is a parallel array, one dword per row.  0 -> the row keeps\n"
    "  // its own format string (a number).  Otherwise it points at a 2-dword\n"
    "  // {text_if_0, text_if_1} pair, and the row renders that instead -- which\n"
    "  // is how a 0/1 switch reads \"off\"/\"on\".  The value is still pushed as\n"
    "  // the format argument either way; a string with no %d just ignores it.\n"
    "  mov esi, [OVL_RPTR]\n"
    "  mov eax, [esi+4]\n"
    "  mov ecx, [eax]\n"
    "  mov eax, [OVL_RCUR]\n"
    "  mov eax, [OVL_ALT+eax*4]\n"
    "  test eax, eax\n"
    "  jz ovl_pick_plain\n"
    "  and ecx, 1\n"
    "  mov eax, [eax+ecx*4]\n"
    "  jmp ovl_pick_done\n"
    "ovl_pick_plain:\n"
    "  mov eax, [esi]\n"
    "ovl_pick_done:\n"
    "  mov [OVL_RTXT], eax\n"
    "  // shadow\n"
    "  mov esi, [OVL_RPTR]\n"
    "  mov eax, [esi+4]\n"
    "  push dword ptr [eax]\n"
    "  push dword ptr [OVL_RTXT]\n"
    "  push 0\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  mov eax, [OVL_RY]\n"
    "  inc eax\n"
    "  push eax\n"
    "  push 19\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  // the row itself\n"
    "  mov esi, [OVL_RPTR]\n"
    "  mov eax, [esi+4]\n"
    "  push dword ptr [eax]\n"
    "  push dword ptr [OVL_RTXT]\n"
    "  mov eax, [OVL_RCUR]\n"
    "  call ovl_getColor\n"
    "  push eax\n"
    "  push ff\n"
    "  push ff\n"
    "  call getTextTexture\n"
    "  add esp, 0c\n"
    "  push eax\n"
    "  push dword ptr [OVL_RY]\n"
    "  push 18\n"
    "  call drawTextTexture\n"
    "  add esp, 14\n"
    "  inc dword ptr [OVL_RCUR]\n"
    "  jmp ovl_draw_row\n"
    "ovl_draw_done:\n"
    "  popad\n"
    "  popfd\n"
    "  ret\n"
    "\n"
    "// =================================================================== //\n"
    "// v0.4.0 -- the two game-side hooks.                                 //\n"
    "// =================================================================== //\n"
    "\n"
    "// ---- No Gameover ---------------------------------------------------- //\n"
    "// (Called \"No Gameover\" rather than \"No Miss\" because it does not stop\n"
    "//  you being hit -- it stops the hit from ending the run.)\n"
    "// Entered from game+B980C, which vanilla spells\n"
    "//     cmp dword ptr [eax+0x48], 0\n"
    "//     jg  game+B9840          ; lives left -> die and respawn\n"
    "//     ...                     ; else -> GAME OVER\n"
    "// eax is already the player object, and the shared `dec [eax+0x48]`\n"
    "// happens later at game+B9894 with nothing reading the field in between\n"
    "// (verified by a full .text sweep).\n"
    "//\n"
    "// v0.7.5 -- lives are NO LONGER smashed to 0.\n"
    "// The old form wrote 1 unconditionally, so the shared `dec` landed on 0\n"
    "// and the very first hit took you from N lives straight to 0 (and every\n"
    "// later hit kept it there).  The user called that out as a nasty side\n"
    "// effect: the feature was fine, the wrecked HUD was not.\n"
    "//\n"
    "// Now the two cases are separated, which is what vanilla itself does:\n"
    "//   * lives > 0 -- take the ordinary death path and let the shared `dec`\n"
    "//     run, so the counter ticks down exactly like vanilla (3 -> 2 -> 1).\n"
    "//   * lives == 0 -- this is the hit vanilla would have ended the run on.\n"
    "//     Fake 1 so the `dec` lands back on 0: the death/respawn animation\n"
    "//     plays and you keep playing with 0 lives.\n"
    "// So the counter never goes negative, it only ever reaches 0 the way the\n"
    "// game itself would, and the run simply never ends.\n"
    "//\n"
    "// The important property is unchanged: with the switch OFF this reproduces\n"
    "// the original two instructions byte for byte, and with it ON lives > 0\n"
    "// still takes the ORIGINAL path -- only the would-have-been-GAME-OVER case\n"
    "// differs.  So a replay is still frame-accurate right up to the first\n"
    "// fatal hit, and the life counter itself matches vanilla until 0.\n"
    "nogameover_hook:\n"
    "  cmp dword ptr [OVL_V_NOGAMEOVER], 0\n"
    "  je nogameover_vanilla\n"
    "  cmp dword ptr [eax+48], 0\n"
    "  jg nogameover_count\n"            # lives left -> let the dec do its job
    "  mov dword ptr [eax+48], 1\n"      # at 0: fake 1 so the dec lands on 0
    "nogameover_count:\n"
    "  inc dword ptr [NOSORE_DEBT]\n"
    "  inc dword ptr [PRB_NOGAMEOVER]\n"
    "  jmp game+B9840\n"
    "nogameover_vanilla:\n"
    "  cmp dword ptr [eax+48], 0\n"
    "  jg game+B9840\n"
    "  jmp game+B9812\n"
    "\n"
    "// ---- freeze power (locks onto whatever power you currently have) ---- //\n"
    "// Replaces the vanilla clamp that closes the player update:\n"
    "//     mov eax, [edi]\n"
    "//     cmp [eax+0x7c], 0      / jge / mov [eax+0x7c], 0\n"
    "//     mov eax, [edi]\n"
    "//     cmp [eax+0x7c], 0x1f4  / jl  / mov [eax+0x7c], 0x1f4\n"
    "//\n"
    "// There is no value to type in: the first frame after the switch goes on\n"
    "// captures the live power into OVL_LP_TARGET, and every frame after that\n"
    "// stores it back.  So power becomes genuinely static -- pickups cannot\n"
    "// raise it and hits cannot lower it.  Switching it off re-arms the\n"
    "// capture, so toggling it re-locks to the power you have right then.\n"
    "// The vanilla path is kept verbatim for when the lock is off.\n"
    "ovl_lockpower:\n"
    "  mov eax, [edi]\n"
    "  // Diagnostic mirror: remember the live player object so an external\n"
    "  // tool can read lives/power straight out of the game (and so the\n"
    "  // later seed/hint work has a pointer to hang off).  One store into\n"
    "  // our own scratch memory, no game state touched.\n"
    "  mov [DBG_PLAYER], eax\n"
    "  cmp dword ptr [OVL_V_LOCKPWR], 0\n"
    "  jne ovl_lp_on\n"
    "  mov dword ptr [OVL_LP_HELD], 0\n"
    "  jmp ovl_lp_vanilla\n"
    "ovl_lp_on:\n"
    "  cmp dword ptr [OVL_LP_HELD], 0\n"
    "  jne ovl_lp_pin\n"
    "  mov edx, [eax+7C]\n"
    "  mov dword ptr [OVL_LP_TARGET], edx\n"
    "  mov dword ptr [OVL_LP_HELD], 1\n"
    "ovl_lp_pin:\n"
    "  mov edx, [OVL_LP_TARGET]\n"
    "  mov dword ptr [eax+7C], edx\n"
    "  inc dword ptr [PRB_LP]\n"
    "  jmp game+B9B26\n"
    "ovl_lp_vanilla:\n"
    "  cmp dword ptr [eax+7C], 0\n"
    "  jge ovl_lp_hi\n"
    "  mov dword ptr [eax+7C], 0\n"
    "ovl_lp_hi:\n"
    "  cmp dword ptr [eax+7C], 1F4\n"
    "  jl ovl_lp_done\n"
    "  mov dword ptr [eax+7C], 1F4\n"
    "ovl_lp_done:\n"
    "  jmp game+B9B26\n"
)

# ---- hint markers (v0.6.0) ---------------------------------------------- //
# A marker is drawn as a `+` made of two filled rectangles rather than with
# drawTextTexture, because that helper takes (fmt, value, colour, x, y) and
# has no size argument at all -- box() gives exact size control, which is what
# the file format's "size" field needs.
#
# The playfield is 384 x ~448 with float coordinates at [[player]+0].  It maps
# into the same 640x480 space the panel uses, offset by (HINT_OX, HINT_OY).
# Those are variables, not immediates, so the origin can be calibrated from
# outside by writing them -- no rebuild per attempt.
HINT_CODE = "\n".join([
    "\n// ---- hint files (v0.6.7) -------------------------------------------- //",
    "// Enumerates <exe dir>\\hint\\*.txt and loads every one that applies, so",
    "// both layouts work with no extra code:",
    "//   * one file per stage   (first line is the stage number)",
    "//   * everything merged    (\"stage N\" lines switch stage mid-file)",
    "// A file whose NAME contains -easy / -normal / -hard / -unreal is only",
    "// used on that difficulty; a name with no such tag applies to all of them.",
    "//",
    "// Everything is UTF-16 because that is what the W APIs want, and",
    "// GetModuleFileNameW hands us the exe path in exactly that form.",
    "//",
    "// Called once per stage.  Preserves all registers.",
    "load_hints:",
    "  pushfd",
    "  pushad",
    "  mov dword ptr [HINT_N], 0",
    "  mov dword ptr [HINT_SKIP], 0",
    "  // The stage the parser keeps.  Prefer the REAL stage the game is running:",
    "  // the stage object carries it at +0x30 (the game copies it there from the",
    "  // global 0xEDDFF0 while setting the stage up -- see the disassembly at",
    "  // RVA 0xB2CB5), and DBG_STAGE is that very object, stored by our",
    "  // initFrameTimer hook immediately above.  This is also correct in a full",
    "  // run, where SEL_STAGE would still read 1 forever.",
    "  mov eax, [DBG_STAGE]",
    "  cmp eax, 10000",
    "  jb load_hints_selstage",
    "  cmp eax, 7FFF0000",
    "  ja load_hints_selstage",
    "  mov eax, [eax+30]",
    "  test eax, eax",
    "  jz load_hints_selstage",
    "  cmp eax, 9",
    "  jbe load_hints_want",
    "load_hints_selstage:",
    "  // Fallback: the practice menu's selection.  SEL_STAGE is 0-based (it",
    "  // indexes SECTION_CNT / MAX_PATTERNID; the menu displays it + 1).",
    "  mov eax, [SEL_STAGE]",
    "  inc eax",
    "  cmp eax, 9",
    "  jbe load_hints_want",
    "  xor eax, eax",
    "load_hints_want:",
    "  mov [HINT_WANT], eax",
    "  // ---- 1. the exe's own path ----",
    "  push 104",                        # 0x104 = 260 WCHARs
    "  push HINT_PATHW",
    "  push 0",
    "  call dword ptr [MODULE_IAT]",
    "  test eax, eax",
    "  jz load_hints_done",
    "  // ---- 2. find the last backslash so we can keep the directory ----",
    "  mov esi, HINT_PATHW",
    "  mov ecx, eax",
    "  xor edx, edx",
    "  xor ebx, ebx",
    "load_hints_scan:",
    "  cmp ebx, ecx",
    "  jae load_hints_cut",
    "  cmp word ptr [esi], 5C",          # '\\'
    "  jne load_hints_next",
    "  mov edx, ebx",
    "load_hints_next:",
    "  add esi, 2",
    "  inc ebx",
    "  jmp load_hints_scan",
    "load_hints_cut:",
    "  inc edx",                        # keep the backslash itself
    "  mov edi, HINT_PATHW",
    "  lea edi, [edi+edx*2]",
    "  // ---- 3. append \"hint\\\" and remember how long the prefix is ----",
    "  mov esi, HINT_PRE",
    "  mov ecx, 5",
    "load_hints_p1:",
    "  mov ax, [esi]",
    "  mov [edi], ax",
    "  add esi, 2",
    "  add edi, 2",
    "  dec ecx",
    "  jnz load_hints_p1",
    "  add edx, 5",
    "  mov [HINT_PRELEN], edx",
    "  // ---- 4. append the search pattern and start enumerating ----",
    "  mov esi, HINT_GLOB",
    "  mov ecx, 5",
    "load_hints_p2:",
    "  mov ax, [esi]",
    "  mov [edi], ax",
    "  add esi, 2",
    "  add edi, 2",
    "  dec ecx",
    "  jnz load_hints_p2",
    "  mov word ptr [edi], 0",
    "  push HINT_FIND",
    "  push HINT_PATHW",
    "  call dword ptr [FINDFIRST_IAT]",
    "  cmp eax, ffffffff",
    "  je load_hints_done",
    "  mov [HINT_FH], eax",
    "load_hints_loop:",
    "  call hint_diff_ok",
    "  test eax, eax",
    "  jz load_hints_skip",
    "  call hint_build_path",
    "  call hint_read_one",
    "  call parse_hints",
    "load_hints_skip:",
    "  push HINT_FIND",
    "  push dword ptr [HINT_FH]",
    "  call dword ptr [FINDNEXT_IAT]",
    "  test eax, eax",
    "  jnz load_hints_loop",
    "  push dword ptr [HINT_FH]",
    "  call dword ptr [FINDCLOSE_IAT]",
    "load_hints_done:",
    "  popad",
    "  popfd",
    "  ret",
    "",
    "// hint_build_path: HINT_PATHW = <dir>\\hint\\ + cFileName.",
    "// The first HINT_PRELEN WCHARs are the prefix and are never overwritten,",
    "// so copying from the start of the same buffer is safe even on the",
    "// second and later files (when the tail no longer holds the pattern).",
    "hint_build_path:",
    "  pushad",
    "  mov esi, HINT_PATHW",
    "  mov edi, HINT_PATHW",
    "  mov ecx, [HINT_PRELEN]",
    "hint_bp_copy:",
    "  mov ax, [esi]",
    "  mov [edi], ax",
    "  add esi, 2",
    "  add edi, 2",
    "  dec ecx",
    "  jnz hint_bp_copy",
    "  mov esi, HINT_FIND",
    "  add esi, 2C",                     # WIN32_FIND_DATAW.cFileName
    "hint_bp_name:",
    "  mov ax, [esi]",
    "  test ax, ax",
    "  jz hint_bp_done",
    "  mov [edi], ax",
    "  add esi, 2",
    "  add edi, 2",
    "  jmp hint_bp_name",
    "hint_bp_done:",
    "  mov word ptr [edi], 0",
    "  popad",
    "  ret",
    "",
    "// hint_diff_ok: does this file apply to the current difficulty?",
    "// Scans cFileName for -easy/-normal/-hard/-unreal (case-folded by ORing",
    "// bit 5 into each UTF-16 unit).  No tag -> applies to every difficulty.",
    "// -> eax = 1 to load, 0 to skip.",
    "hint_diff_ok:",
    "  pushad",
    "  mov esi, HINT_FIND",
    "  add esi, 2C",
    "hint_diff_scan:",
    "  mov ax, [esi]",
    "  test ax, ax",
    "  jz hint_diff_none",
    "  cmp ax, 2D",                      # '-'
    "  jne hint_diff_next",
    "  mov eax, [esi+2]",                # the next two UTF-16 units
    "  or eax, 200020",                  # fold to lower case
    "  cmp eax, 610065",                 # 'ea' -> easy
    "  je hint_diff_easy",
    "  cmp eax, 6F006E",                 # 'no' -> normal
    "  je hint_diff_normal",
    "  cmp eax, 610068",                 # 'ha' -> hard
    "  je hint_diff_hard",
    "  cmp eax, 6E0075",                 # 'un' -> unreal
    "  je hint_diff_unreal",
    "hint_diff_next:",
    "  add esi, 2",
    "  jmp hint_diff_scan",
    "hint_diff_easy:",
    "  xor ebx, ebx",
    "  jmp hint_diff_cmp",
    "hint_diff_normal:",
    "  mov ebx, 1",
    "  jmp hint_diff_cmp",
    "hint_diff_hard:",
    "  mov ebx, 2",
    "  jmp hint_diff_cmp",
    "hint_diff_unreal:",
    "  mov ebx, 3",
    "hint_diff_cmp:",
    "  mov eax, [SEL_DIFF]",
    "  cmp eax, 3",
    "  jbe hint_diff_have",
    "  xor eax, eax",
    "hint_diff_have:",
    "  cmp ebx, eax",
    "  jne hint_diff_no",
    "  mov dword ptr [HINT_OK], 1",
    "  jmp hint_diff_out",
    "hint_diff_none:",
    "  mov dword ptr [HINT_OK], 1",     # untagged -> every difficulty
    "  jmp hint_diff_out",
    "hint_diff_no:",
    "  mov dword ptr [HINT_OK], 0",
    "hint_diff_out:",
    "  popad",
    "  mov eax, [HINT_OK]",
    "  ret",
    "",
    "// hint_read_one: slurp HINT_PATHW into HINT_BUF, set HINT_LEN.",
    "hint_read_one:",
    "  pushad",
    "  mov dword ptr [HINT_LEN], 0",
    "  mov dword ptr [HINT_GOT], 0",
    "  push 0",
    "  push 80",
    "  push 3",                          # OPEN_EXISTING
    "  push 0",
    "  push 1",                          # FILE_SHARE_READ
    "  push 80000000",                   # GENERIC_READ
    "  push HINT_PATHW",
    "  call dword ptr [FILE_IAT]",
    "  cmp eax, ffffffff",
    "  je hint_read_done",
    "  mov [HINT_HANDLE], eax",
    "  push 0",
    "  push HINT_GOT",
    "  push dword ptr [HINT_BUFMAX]",     # the VALUE, not the address
    "  push HINT_BUF",
    "  push eax",
    "  call dword ptr [READ_IAT]",
    "  mov eax, [HINT_GOT]",
    "  mov [HINT_LEN], eax",
    "  push dword ptr [HINT_HANDLE]",
    "  call dword ptr [CLOSE_IAT]",
    "hint_read_done:",
    "  popad",
    "  ret",
    "",
    "// ---- hint markers (v0.6.3) ------------------------------------------ //",
    "// Walks HINT_ARR and draws every entry whose time window contains the",
    "// current stage frame.  Two shapes, chosen by the entry's marker char:",
    "//   '+'  a crosshair, drawn as two filled rectangles",
    "//   '-'  a full-width horizontal dashed line (a \"safe line\")",
    "// box() is used rather than drawTextTexture because that helper takes",
    "// (fmt, value, colour, x, y) and has NO size argument at all.",
    "//",
    "// box() is a game function and does not preserve ecx/edx/esi, so every",
    "// coordinate is reloaded from memory for each rectangle.  Relying on the",
    "// registers surviving a call silently drew the second bar off-screen.",
    "//",
    "// Entry layout (0x30 = 48 bytes):",
    "//   +00 mark  +04 size  +08 char  +0C x  +10 y",
    "//   +14 start kind  +18 start pattern  +1C start frame",
    "//   +20 end kind    +24 end pattern    +28 end frame",
    "//",
    "// v0.7.5 -- BOTH bounds are HALF-OPEN: the window is the set of positions",
    "// (pattern, frame) with start <= pos < end.  The end bound is therefore",
    "// exclusive, which makes \"boss:N:0\" as the END mean \"until pattern N",
    "// starts\" -- i.e. exactly \"until the pattern before it ends\" -- and that is",
    "// what the F2 capture writes.  The previous inclusive end stayed open for",
    "// the first frame of the end pattern, which showed the mid non-spell hint",
    "// bleeding into the mid spell (and the spell-1 hint into non 2).\n"
    "draw_hints:",
    "  pushfd",
    "  pushad",
    "  mov dword ptr [HINT_CUR], 0",     # walk the array from the start each frame
    "  // The player's playfield position, once: it is both the fade reference",
    "  // and what the calibration mirrors report.  DBG_PLAYER is only refreshed",
    "  // while a stage is running, so range-check it.",
    "  mov dword ptr [DBG_PX], 0",
    "  mov dword ptr [DBG_PY], 0",
    "  mov eax, [DBG_PLAYER]",
    "  cmp eax, 10000",
    "  jb draw_hints_loop",
    "  cmp eax, 7FFF0000",
    "  ja draw_hints_loop",
    "  mov eax, [eax]",
    "  cmp eax, 10000",
    "  jb draw_hints_loop",
    "  cmp eax, 7FFF0000",
    "  ja draw_hints_loop",
    "  cvttss2si ecx, dword ptr [eax]",
    "  cvttss2si edx, dword ptr [eax+4]",
    "  mov [DBG_PX], ecx",
    "  mov [DBG_PY], edx",
    "draw_hints_loop:",
    "  mov eax, [HINT_CUR]",
    "  cmp eax, [HINT_N]",
    "  jae draw_hints_done",
    "  imul eax, eax, 30",
    "  add eax, HINT_ARR",
    "  mov [HINT_ROW], eax",
    "  // ---- character filter ----",
    "  // Entry +8 is 0 for \"every character\", else 1..4.  CHAR_IDX is the game",
    "  // global the practice menu's per-character bomb default reads",
    "  // (game+ADDFEC, 0-based).  NOTE: that mapping is inherited from le03 and",
    "  // reads 0 for the default character, so a per-character hint is only as",
    "  // trustworthy as that global -- see the README.",
    "  mov eax, [HINT_ROW]",
    "  cmp dword ptr [eax+8], 0",
    "  je draw_hints_char_ok",
    "  mov ecx, [game+ADDFEC]",
    "  inc ecx",
    "  cmp ecx, [eax+8]",
    "  jne draw_hints_next",
    "draw_hints_char_ok:",
    "  // ---- time window ----",
    "  // Two forms, and BOTH ends must agree on which one they use.  A mixed",
    "  // pair (boss start, absolute end) is skipped rather than guessed at --",
    "  // silently picking one would show the hint at a meaningless time.",
    "  mov esi, [HINT_ROW]",
    "  mov eax, [esi+14]",              # start kind: 0 = frame, 1 = boss
    "  cmp eax, [esi+20]",              # end kind must match
    "  jne draw_hints_next",
    "  test eax, eax",
    "  jnz draw_hints_boss",
    "  // ---- form 0: absolute stage frames ----",
    "  mov eax, [DBG_STAGE]",
    "  cmp eax, 10000",
    "  jb draw_hints_next",
    "  cmp eax, 7FFF0000",
    "  ja draw_hints_next",
    "  mov eax, [eax+4C]",
    "  cmp eax, [esi+1C]",
    "  jb draw_hints_next",
    "  // v0.7.5: exclusive end here too, so the two forms agree.\n"
    "  cmp eax, [esi+28]",
    "  jae draw_hints_next",
    "  jmp draw_hints_boss_ok",
    "  // ---- form 1: boss patterns ----",
    "  // The current position is the pair (pattern index, pattern-relative",
    "  // frame) and it is compared against (start, end) LEXICOGRAPHICALLY, so",
    "  // one window may legitimately span several patterns -- e.g. from",
    "  // boss:2:60 to boss:4:0 covers the tail of pattern 2 and all of 3.",
    "draw_hints_boss:",
    "  // Gate on \"a boss is on screen\", never on the pattern number: pattern 0",
    "  // is the mid non-spell, so testing the number for zero would throw away",
    "  // the first pattern of every stage.",
    "  cmp dword ptr [HINT_PAT_ON], 0",
    "  je draw_hints_next",
    "  mov eax, [HINT_PAT_IDX]",
    "  mov edx, [HINT_PAT_FRAME]",      # frames into the current pattern
    "  cmp eax, [esi+18]",              # against the start pattern
    "  jb draw_hints_next",
    "  ja draw_hints_boss_start",
    "  cmp edx, [esi+1C]",              # same pattern -> check the start frame
    "  jb draw_hints_next",
    "draw_hints_boss_start:",
    "  // ---- v0.7.5: the END bound is EXCLUSIVE (half-open [start, end)) ----",
    "  // Before this, both ends were inclusive, so a window ending at\n"
    "  // boss:4:0 stayed open for the whole first frame of pattern 4.  That is\n"
    "  // exactly what the user saw: the mid non-spell window (ending boss:1:0)\n"
    "  // still lit through the opening of the mid spell, and the stage-boss\n"
    "  // spell-1 window (ending boss:5:0) lit through the opening of non 2.\n"
    "  //\n"
    "  // The capture output already writes end = boss:<idx+1>:0 for \"until\n"
    "  // this pattern ends\", which is only correct under half-open semantics:\n"
    "  // the window must close the instant the NEXT pattern begins.\n"
    "  cmp eax, [esi+24]",              # against the end pattern
    "  ja draw_hints_next",             # past the end pattern -> closed
    "  jb draw_hints_boss_ok",          # an earlier pattern -> window is open
    "  mov eax, [HINT_PAT_FRAME]",      # same pattern: (frame) < end frame?
    "  cmp eax, [esi+28]",
    "  jae draw_hints_next",            # reached the end frame -> closed
    "draw_hints_boss_ok:",
    "  // ---- colour: dim it when the player is standing on the marker ----",
    "  mov eax, [DBG_PX]",
    "  sub eax, [esi+0C]",
    "  test eax, eax",
    "  jns draw_hints_adx",
    "  neg eax",
    "draw_hints_adx:",
    "  mov ebx, [DBG_PY]",
    "  sub ebx, [esi+10]",
    "  test ebx, ebx",
    "  jns draw_hints_ady",
    "  neg ebx",
    "draw_hints_ady:",
    "  add eax, ebx",                     # manhattan distance is enough here
    "  mov ecx, [HINT_COL]",
    "  cmp eax, [HINT_FADE_R]",
    "  jae draw_hints_col",
    "  mov ecx, [HINT_COL_DIM]",
    "draw_hints_col:",
    "  mov [HINT_USECOL], ecx",
    "  // ---- marker position: playfield + fix + playfield origin ----",
    "  mov ecx, [esi+0C]",
    "  mov edx, [esi+10]",
    "  mov eax, [HINT_DX]",
    "  sub eax, 40",
    "  add ecx, eax",
    "  mov eax, [HINT_DY]",
    "  sub eax, 40",
    "  add edx, eax",
    "  add ecx, [HINT_OX]",
    "  add edx, [HINT_OY]",
    "  mov [HINT_CX], ecx",
    "  mov [HINT_CY], edx",
    "  mov eax, [esi+4]",
    "  mov [HINT_SIZE], eax",
    "  shr eax, 1",
    "  mov [HINT_HALF], eax",
    "  cmp dword ptr [esi], 2D",          # '-'
    "  je draw_hints_dash",
    "  cmp dword ptr [esi], 7C",          # '|'
    "  je draw_hints_vline",
    "  // ---- the crosshair ----",
    "  mov ecx, [HINT_CX]",
    "  mov edx, [HINT_CY]",
    "  mov esi, [HINT_HALF]",
    "  mov eax, ecx",
    "  sub eax, esi",
    "  mov ebx, ecx",
    "  add ebx, esi",
    "  mov edi, edx",
    "  inc edi",
    "  push 1",
    "  push dword ptr [HINT_USECOL]",
    "  push edi",
    "  push ebx",
    "  push edx",
    "  push eax",
    "  call box",
    "  add esp, 18",
    "  mov ecx, [HINT_CX]",
    "  mov edx, [HINT_CY]",
    "  mov esi, [HINT_HALF]",
    "  mov eax, edx",
    "  sub eax, esi",
    "  mov ebx, edx",
    "  add ebx, esi",
    "  mov edi, ecx",
    "  inc edi",
    "  push 1",
    "  push dword ptr [HINT_USECOL]",
    "  push ebx",
    "  push edi",
    "  push eax",
    "  push ecx",
    "  call box",
    "  add esp, 18",
    "  jmp draw_hints_next",
    "  // ---- the dashed safe line ----",
    "  // Spans the whole playfield width at the marker's y; the marker's x is",
    "  // irrelevant, which is why the capture tool can still write a point and",
    "  // you just change the symbol in the txt.",
    "draw_hints_dash:",
    "  mov eax, [HINT_SIZE]",
    "  shr eax, 1",
    "  test eax, eax",
    "  jnz draw_hints_dash_len",
    "  mov eax, 8",
    "draw_hints_dash_len:",
    "  mov [HINT_DASHLEN], eax",
    "  mov eax, [HINT_OX]",
    "  mov [HINT_CX], eax",
    "  add eax, 180",                    # 0x180 = 384 = the playfield width
    "  mov [HINT_DASHEND], eax",
    "draw_hints_dash_loop:",
    "  mov eax, [HINT_CX]",
    "  cmp eax, [HINT_DASHEND]",
    "  jae draw_hints_next",
    "  mov ebx, eax",
    "  add ebx, [HINT_DASHLEN]",
    "  cmp ebx, [HINT_DASHEND]",
    "  jbe draw_hints_dash_seg",
    "  mov ebx, [HINT_DASHEND]",
    "draw_hints_dash_seg:",
    "  mov ecx, [HINT_CY]",
    "  mov edx, ecx",
    "  inc edx",
    "  push 1",
    "  push dword ptr [HINT_USECOL]",
    "  push edx",
    "  push ebx",
    "  push ecx",
    "  push eax",
    "  call box",
    "  add esp, 18",
    "  mov eax, [HINT_DASHLEN]",
    "  add eax, eax",
    "  add [HINT_CX], eax",
    "  jmp draw_hints_dash_loop",
    "  // ---- the vertical safe line ('|') ----",
    "  // The exact mirror of the dash above: it spans the whole playfield",
    "  // HEIGHT at the marker's x, so the marker's y is irrelevant and only the",
    "  // x column matters.  Same dash length rule (size/2, gap = dash).",
    "draw_hints_vline:",
    "  mov eax, [HINT_SIZE]",
    "  shr eax, 1",
    "  test eax, eax",
    "  jnz draw_hints_vl_len",
    "  mov eax, 8",
    "draw_hints_vl_len:",
    "  mov [HINT_DASHLEN], eax",
    "  mov eax, [HINT_OY]",
    "  mov [HINT_CY], eax",
    "  add eax, 1C0",                    # 0x1C0 = 448 = the playfield height
    "  mov [HINT_DASHEND], eax",
    "draw_hints_vl_loop:",
    "  mov eax, [HINT_CY]",
    "  cmp eax, [HINT_DASHEND]",
    "  jae draw_hints_next",
    "  mov ebx, eax",
    "  add ebx, [HINT_DASHLEN]",
    "  cmp ebx, [HINT_DASHEND]",
    "  jbe draw_hints_vl_seg",
    "  mov ebx, [HINT_DASHEND]",
    "draw_hints_vl_seg:",
    "  mov ecx, [HINT_CX]",
    "  mov edx, ecx",
    "  inc edx",
    "  push 1",
    "  push dword ptr [HINT_USECOL]",
    "  push ebx",                        # y2 = y1 + dash
    "  push edx",                        # x2 = x1 + 1
    "  push eax",                        # y1
    "  push ecx",                        # x1
    "  call box",
    "  add esp, 18",
    "  mov eax, [HINT_DASHLEN]",
    "  add eax, eax",
    "  add [HINT_CY], eax",
    "  jmp draw_hints_vl_loop",
    "draw_hints_next:",
    "  inc dword ptr [HINT_CUR]",
    "  jmp draw_hints_loop",
    "draw_hints_done:",
    "  popad",
    "  popfd",
    "  ret",
    "",
    "// draw_pcross (v0.7.8): the self-machine judgement-point cross ---- //",
    "// Ported from le03's `Player +` row.  It is drawn from the SAME playfield",
    "// position, through the SAME transform the hint markers use --",
    "//     game coord = pos + (Fix - 0x40) + HINT_OX/HINT_OY",
    "// -- so with Fix X/Y at their neutral 0x40 the cross sits exactly on the",
    "// judgement dot AND exactly on any hint marker placed there, and one Fix",
    "// nudge moves both together.  It is gated by its OWN switch, NOT by Hint,",
    "// so turning the hint markers off does not take the cross away.",
    "//",
    "// le02 draws in the game's own 640x480 logical space (box() scales it),",
    "// so unlike le03 there is no client-scale arithmetic here at all -- which",
    "// is also why the cross is sized in LOGICAL units (see below), not in the",
    "// screen pixels le03 can use directly.",
    "//",
    "// v0.7.8: the size.  v0.7.7 copied le03's arm-12 numbers verbatim, which in",
    "// this logical space is ~80 screen px -- over three times le03's 25 px.  It",
    "// is now arm 4 / 1 logical px thick = ~27 x 3 screen px, matching le03.",
    "draw_pcross:",
    "  pushfd",
    "  pushad",
    "  // Zero the mirrors first, exactly as draw_hints does: DBG_PLAYER is only",
    "  // refreshed while a stage is running, and a stale pair would otherwise",
    "  // survive into the hint fade test when Hint is off.",
    "  mov dword ptr [DBG_PX], 0",
    "  mov dword ptr [DBG_PY], 0",
    "  cmp dword ptr [OVL_V_PCROSS], 0",
    "  je ovl_pc_done",
    "  // ---- the player's playfield position (the same read draw_hints does)",
    "  mov eax, [DBG_PLAYER]",
    "  cmp eax, 10000",
    "  jb ovl_pc_done",
    "  cmp eax, 7FFF0000",
    "  ja ovl_pc_done",
    "  mov eax, [eax]",
    "  cmp eax, 10000",
    "  jb ovl_pc_done",
    "  cmp eax, 7FFF0000",
    "  ja ovl_pc_done",
    "  cvttss2si ecx, dword ptr [eax]",
    "  cvttss2si edx, dword ptr [eax+4]",
    "  mov [DBG_PX], ecx",
    "  mov [DBG_PY], edx",
    "  // ---- playfield + Fix + origin, byte for byte what draw_hints does ----",
    "  mov eax, [HINT_DX]",
    "  sub eax, 40",
    "  add ecx, eax",
    "  add ecx, [HINT_OX]",
    "  mov eax, [HINT_DY]",
    "  sub eax, 40",
    "  add edx, eax",
    "  add edx, [HINT_OY]",
    "  mov [HINT_CX], ecx",
    "  mov [HINT_CY], edx",
    "  // ---- horizontal bar ----",
    "  // arm 4, 1 px thick.  le02's box() works in the game's own 640x480",
    "  // logical space, which the window then stretches by ~3.33x (2560x1600),",
    "  // so a logical unit is ~3.3 screen px.  le03's cross is 25 x 3 SCREEN px,",
    "  // i.e. ~7.5 x 1 logical here -- drawing it at le03's literal numbers",
    "  // (arm 12) came out ~80 px wide, which is what the user spotted.  box()",
    "  // is half-open on x1/y1, so a bar spans (x1-x0) x (y1-y0) logical px.",
    "  mov ecx, [HINT_CX]",
    "  mov edx, [HINT_CY]",
    "  mov eax, ecx",
    "  sub eax, 4",
    "  mov ebx, ecx",
    "  add ebx, 4",
    "  mov esi, edx",
    "  mov edi, edx",
    "  inc edi",
    "  push 1",
    "  push dword ptr [HINT_COL]",
    "  push edi",
    "  push ebx",
    "  push esi",
    "  push eax",
    "  call box",
    "  add esp, 18",
    "  // ---- vertical bar ----",
    "  // box() clobbers ecx/edx/esi, so reload every coordinate from memory.",
    "  mov ecx, [HINT_CX]",
    "  mov edx, [HINT_CY]",
    "  mov esi, ecx",
    "  mov edi, ecx",
    "  inc edi",
    "  mov eax, edx",
    "  sub eax, 4",
    "  mov ebx, edx",
    "  add ebx, 4",
    "  push 1",
    "  push dword ptr [HINT_COL]",
    "  push ebx",
    "  push edi",
    "  push eax",
    "  push esi",
    "  call box",
    "  add esp, 18",
    "ovl_pc_done:",
    "  popad",
    "  popfd",
    "  ret",
    "",
])

# ---- hint parser (v0.6.3) ------------------------------------------------ //
# Turns HINT_BUF (text) into HINT_ARR.  The format is deliberately trivial to
# parse: everything is separated by whitespace, commas or colons, comments run
# from '#' to end of line, and a line is either
#     <stage-number>                      the file header
#     stage <number>                      switches stage mid-file (merged files)
#     <mark> <size> <char> <start> <x> <y> <end>
# where <start>/<end> are either a bare frame number or "boss P F".
#
# HINT_MAXN caps the array; extra lines are counted in HINT_SKIP rather than
# overflowing.
HINT_PARSE = "\n".join([
    "\n// ---- hint parsing (v0.6.3) ------------------------------------------ //",
    "// hint_skip: advance HINT_P past separators, blank lines and comments.",
    "hint_skip:",
    "  mov esi, [HINT_P]",
    "  mov edi, [HINT_END]",
    "hint_skip_loop:",
    "  cmp esi, edi",
    "  jae hint_skip_done",
    "  mov al, [esi]",
    "  cmp al, 23",                      # '#'
    "  je hint_skip_comment",
    "  cmp al, 20",                      # ' '
    "  je hint_skip_adv",
    "  cmp al, 09",                      # tab
    "  je hint_skip_adv",
    "  cmp al, 0D",
    "  je hint_skip_adv",
    "  cmp al, 0A",
    "  je hint_skip_adv",
    "  cmp al, 2C",                      # ','
    "  je hint_skip_adv",
    "  cmp al, 3A",                      # ':'
    "  je hint_skip_adv",
    "  jmp hint_skip_done",
    "hint_skip_adv:",
    "  inc esi",
    "  jmp hint_skip_loop",
    "hint_skip_comment:",
    "  inc esi",
    "  cmp esi, edi",
    "  jae hint_skip_done",
    "  cmp byte ptr [esi], 0A",
    "  jne hint_skip_comment",
    "  inc esi",
    "  jmp hint_skip_loop",
    "hint_skip_done:",
    "  mov [HINT_P], esi",
    "  ret",
    "",
    "// hint_tok: copy the next token into HINT_TOK (NUL-terminated).",
    "// Returns its length in eax.",
    "hint_tok:",
    "  call hint_skip",
    "  mov esi, [HINT_P]",
    "  mov edi, [HINT_END]",
    "  mov edx, HINT_TOK",
    "  xor ecx, ecx",
    "hint_tok_loop:",
    "  cmp esi, edi",
    "  jae hint_tok_done",
    "  mov al, [esi]",
    "  cmp al, 20",
    "  je hint_tok_done",
    "  cmp al, 09",
    "  je hint_tok_done",
    "  cmp al, 0D",
    "  je hint_tok_done",
    "  cmp al, 0A",
    "  je hint_tok_done",
    "  cmp al, 2C",
    "  je hint_tok_done",
    "  cmp al, 3A",
    "  je hint_tok_done",
    "  cmp al, 23",
    "  je hint_tok_done",
    "  cmp ecx, 18",                     # 0x18 = 24 chars max
    "  jae hint_tok_adv",
    "  mov [edx], al",
    "  inc edx",
    "  inc ecx",
    "hint_tok_adv:",
    "  inc esi",
    "  jmp hint_tok_loop",
    "hint_tok_done:",
    "  mov byte ptr [edx], 0",
    "  mov [HINT_P], esi",
    "  mov eax, ecx",
    "  ret",
    "",
    "// hint_atoi: decimal HINT_TOK -> eax (0 if it is not a number).",
    "hint_atoi:",
    "  mov esi, HINT_TOK",
    "  xor eax, eax",
    "hint_atoi_loop:",
    "  movzx edx, byte ptr [esi]",
    "  test edx, edx",
    "  jz hint_atoi_done",
    "  cmp edx, 30",
    "  jb hint_atoi_done",
    "  cmp edx, 39",
    "  ja hint_atoi_done",
    "  imul eax, eax, 0A",
    "  sub edx, 30",
    "  add eax, edx",
    "  inc esi",
    "  jmp hint_atoi_loop",
    "hint_atoi_done:",
    "  ret",
    "",
    "// hint_time: parse one time spec into HINT_TKIND / HINT_TPAT / HINT_TFR.",
    "//   \"1200\"      -> kind 0, frame 1200 (absolute stage frame)",
    "//   \"boss:2:60\" -> kind 1, pattern 2, frame 60 (relative to the pattern)",
    "hint_time:",
    "  call hint_tok",
    "  mov dword ptr [HINT_TKIND], 0",
    "  mov dword ptr [HINT_TPAT], 0",
    "  mov dword ptr [HINT_TFR], 0",
    "  mov esi, HINT_TOK",
    "  movzx eax, byte ptr [esi]",
    "  or al, 20",                       # lowercase
    "  cmp al, 62",                      # 'b' of boss
    "  jne hint_time_num",
    "  mov dword ptr [HINT_TKIND], 1",
    "  call hint_tok",
    "  call hint_atoi",
    "  mov [HINT_TPAT], eax",
    "  call hint_tok",
    "  call hint_atoi",
    "  mov [HINT_TFR], eax",
    "  ret",
    "hint_time_num:",
    "  call hint_atoi",
    "  mov [HINT_TFR], eax",
    "  ret",
    "",
    "// hint_store: copy the HINT_E_* scratch into the array at index HINT_N.",
    "hint_store:",
    "  mov eax, [HINT_N]",
    "  imul eax, eax, 30",               # 0x30 = 48 bytes per entry
    "  add eax, HINT_ARR",
    "  mov ecx, [HINT_E_MARK]",
    "  mov [eax], ecx",
    "  mov ecx, [HINT_E_SIZE]",
    "  mov [eax+4], ecx",
    "  mov ecx, [HINT_E_CHAR]",
    "  mov [eax+8], ecx",
    "  mov ecx, [HINT_E_X]",
    "  mov [eax+0C], ecx",
    "  mov ecx, [HINT_E_Y]",
    "  mov [eax+10], ecx",
    "  mov ecx, [HINT_E_SK]",
    "  mov [eax+14], ecx",
    "  mov ecx, [HINT_E_SP]",
    "  mov [eax+18], ecx",
    "  mov ecx, [HINT_E_SF]",
    "  mov [eax+1C], ecx",
    "  mov ecx, [HINT_E_EK]",
    "  mov [eax+20], ecx",
    "  mov ecx, [HINT_E_EP]",
    "  mov [eax+24], ecx",
    "  mov ecx, [HINT_E_EF]",
    "  mov [eax+28], ecx",
    "  inc dword ptr [HINT_N]",
    "  ret",
    "",
    "// parse_hints: the main pass.  HINT_WANT holds the stage to keep.",
    "parse_hints:",
    "  pushfd",
    "  pushad",
    "  // HINT_N / HINT_SKIP are reset once by load_hints, not here: it\n"
    "  // calls parse_hints once per file and the counts must accumulate.\n"
    "  mov dword ptr [HINT_CURSTAGE], 0",
    "  mov eax, HINT_BUF",
    "  mov [HINT_P], eax",
    "  add eax, [HINT_LEN]",
    "  mov [HINT_END], eax",
    "parse_loop:",
    "  call hint_skip",
    "  mov eax, [HINT_P]",
    "  cmp eax, [HINT_END]",
    "  jae parse_done",
    "  call hint_tok",
    "  test eax, eax",
    "  jz parse_done",
    "  // A first token that is a bare number, or the word \"stage\" followed by",
    "  // one, is a stage header rather than a marker.  (The word form is what",
    "  // lets a single merged file carry several stages.)",
    "  cmp eax, 5",                      # len(\"stage\")
    "  jne parse_not_stage",
    "  movzx eax, byte ptr [HINT_TOK]",
    "  or al, 20",
    "  cmp al, 73",                      # 's'
    "  je parse_stage_word",
    "parse_not_stage:",
    "  movzx eax, byte ptr [HINT_TOK]",
    "  cmp eax, 30",
    "  jb parse_hint",
    "  cmp eax, 39",
    "  ja parse_hint",
    "  call hint_atoi",
    "  mov [HINT_CURSTAGE], eax",
    "  jmp parse_loop",
    "parse_stage_word:",
    "  call hint_tok",
    "  call hint_atoi",
    "  mov [HINT_CURSTAGE], eax",
    "  jmp parse_loop",
    "parse_hint:",
    "  movzx eax, byte ptr [HINT_TOK]",
    "  mov [HINT_E_MARK], eax",
    "  call hint_tok",                  # size
    "  call hint_atoi",
    "  mov [HINT_E_SIZE], eax",
    "  call hint_tok",                  # character filter
    "  // Stored as 0 = every character, or 1..4 = that character in the game's",
    "  // own order.  Anything unrecognised stays 0: failing OPEN is deliberate,",
    "  // because an unknown name must never silently hide a hint.",
    "  mov dword ptr [HINT_E_CHAR], 0",
    "  mov esi, HINT_TOK",
    "  movzx eax, byte ptr [esi]",
    "  cmp eax, 31",                     # '1'
    "  jb parse_char_done",
    "  cmp eax, 34",                     # '4'
    "  ja parse_char_done",
    "  cmp byte ptr [esi+1], 0",         # a single character, not \"1abc\"
    "  jne parse_char_done",
    "  sub eax, 30",
    "  mov [HINT_E_CHAR], eax",
    "parse_char_done:",
    "  call hint_time",                 # start
    "  mov eax, [HINT_TKIND]",
    "  mov [HINT_E_SK], eax",
    "  mov eax, [HINT_TPAT]",
    "  mov [HINT_E_SP], eax",
    "  mov eax, [HINT_TFR]",
    "  mov [HINT_E_SF], eax",
    "  call hint_tok",                  # x
    "  call hint_atoi",
    "  mov [HINT_E_X], eax",
    "  call hint_tok",                  # y
    "  call hint_atoi",
    "  mov [HINT_E_Y], eax",
    "  call hint_time",                 # end",
    "  mov eax, [HINT_TKIND]",
    "  mov [HINT_E_EK], eax",
    "  mov eax, [HINT_TPAT]",
    "  mov [HINT_E_EP], eax",
    "  mov eax, [HINT_TFR]",
    "  mov [HINT_E_EF], eax",
    "  // Keep only entries belonging to the stage we loaded for.",
    "  mov eax, [HINT_CURSTAGE]",
    "  cmp eax, [HINT_WANT]",
    "  jne parse_skip",
    "  cmp dword ptr [HINT_N], HINT_MAXN",
    "  jae parse_skip",
    "  call hint_store",
    "  jmp parse_loop",
    "parse_skip:",
    "  inc dword ptr [HINT_SKIP]",
    "  jmp parse_loop",
    "parse_done:",
    "  popad",
    "  popfd",
    "  ret",
    "",
])

# ---- capture (v0.6.4) ---------------------------------------------------- //
# Writes the player's current spot into hint/<stage>.txt as one more line.
# Appends rather than rewrites, so hand-written entries survive.
#
# The coordinates stored are the RAW playfield values, not the calibrated
# ones: the Fix X / Fix Y correction is applied when drawing, so keeping the
# file in raw coordinates means one correction covers every entry.
#
# The end of the window is the end of the 道中 chapter the player is in,
# computed from BAN's SECTION_TABLE.  Past the last chapter (i.e. in the boss
# fight) there is no per-pattern table, so it falls back to frame+300 as a
# sane default you can edit.
HINT_CAPTURE = "\n".join([
    "\n// ---- capture (v0.6.4) ------------------------------------------------ //",
    "// hint_itoa: eax = value, edi = destination.  Writes decimal digits and",
    "// advances edi.  pushad would undo edi, so the new value is stashed.",
    "hint_itoa:",
    "  pushad",
    "  mov ebx, 0A",
    "  xor ecx, ecx",
    "  test eax, eax",
    "  jnz hint_itoa_loop",
    "  mov byte ptr [edi], 30",
    "  inc edi",
    "  jmp hint_itoa_out",
    "hint_itoa_loop:",
    "  xor edx, edx",
    "  div ebx",
    "  add edx, 30",
    "  push edx",
    "  inc ecx",
    "  test eax, eax",
    "  jnz hint_itoa_loop",
    "hint_itoa_pop:",
    "  pop eax",
    "  mov [edi], al",
    "  inc edi",
    "  dec ecx",
    "  jnz hint_itoa_pop",
    "hint_itoa_out:",
    "  mov [HINT_IEDI], edi",
    "  popad",
    "  mov edi, [HINT_IEDI]",
    "  ret",
    "",
    "// hint_emit_time: write one time spec at edi and advance it.",
    "//   eax = kind (0 = absolute stage frame, 1 = boss pattern)",
    "//   ecx = pattern index (kind 1 only)",
    "//   edx = frame",
    "// kind 0 -> \"<frame>\"      kind 1 -> \"boss:<pattern>:<frame>\"",
    "// hint_itoa preserves ecx/edx (it brackets its work with pushad/popad), so",
    "// the second call still sees the frame.",
    "hint_emit_time:",
    "  test eax, eax",
    "  jz hint_emit_abs",
    "  mov byte ptr [edi], 62",          # 'b'
    "  mov byte ptr [edi+1], 6F",        # 'o'
    "  mov byte ptr [edi+2], 73",        # 's'
    "  mov byte ptr [edi+3], 73",        # 's'
    "  mov byte ptr [edi+4], 3A",        # ':'
    "  add edi, 5",
    "  mov eax, ecx",
    "  call hint_itoa",
    "  mov byte ptr [edi], 3A",          # ':'
    "  inc edi",
    "  mov eax, edx",
    "  call hint_itoa",
    "  ret",
    "hint_emit_abs:",
    "  mov eax, edx",
    "  call hint_itoa",
    "  ret",
    "",
    "// hint_chapter_end: end frame of the chapter containing HINT_C_F.",
    "// SECTION_TABLE[stage] points at a per-chapter frame-count list (dwords),",
    "// indexed 0-based -- and HINT_WANT is the REAL 1-based stage (see",
    "// load_hints), so this is HINT_WANT-1.  Using SEL_STAGE here was wrong in",
    "// a full run for exactly the same reason it was wrong in load_hints.",
    "hint_chapter_end:",
    "  pushad",
    "  mov eax, [HINT_WANT]",
    "  test eax, eax",
    "  jz hint_chap_ok",                 # 0 -> index 0
    "  dec eax",
    "  cmp eax, 6",
    "  jbe hint_chap_ok",
    "  xor eax, eax",
    "hint_chap_ok:",
    "  mov esi, [SECTION_TABLE+eax*4]",
    "  movzx ecx, byte ptr [SECTION_CNT+eax]",
    "  xor edx, edx",
    "hint_chap_loop:",
    "  test ecx, ecx",
    "  jz hint_chap_out",
    "  mov eax, [esi]",
    "  add edx, eax",
    "  cmp edx, [HINT_C_F]",
    "  jae hint_chap_hit",
    "  add esi, 4",
    "  dec ecx",
    "  jmp hint_chap_loop",
    "hint_chap_hit:",
    "  mov [HINT_CHAP_END], edx",
    "  jmp hint_chap_fin",
    "hint_chap_out:",
    "  mov eax, [HINT_C_F]",
    "  add eax, 12C",                    # 0x12C = 300 frames
    "  mov [HINT_CHAP_END], eax",
    "hint_chap_fin:",
    "  popad",
    "  mov eax, [HINT_CHAP_END]",
    "  ret",
    "",
    "// hint_cap_path: HINT_PATHW = <dir>\\hint\\ + <HINT_WANT>.txt.",
    "// The first HINT_PRELEN WCHARs are the directory prefix load_hints already",
    "// worked out (and they are still in the buffer), so only the file name has",
    "// to be written.  Copying from the start of the same buffer is safe because",
    "// the destination never overtakes the source.",
    "hint_cap_path:",
    "  pushad",
    "  mov esi, HINT_PATHW",
    "  mov edi, HINT_PATHW",
    "  mov ecx, [HINT_PRELEN]",
    "  test ecx, ecx",
    "  jz hint_cp_done",                 # no prefix -> nothing we can build",
    "hint_cp_copy:",
    "  mov ax, [esi]",
    "  mov [edi], ax",
    "  add esi, 2",
    "  add edi, 2",
    "  dec ecx",
    "  jnz hint_cp_copy",
    "  // One UTF-16 digit for the stage.  Stages are 1..7 and load_hints",
    "  // already clamps HINT_WANT to 0..9, so one character always suffices.",
    "  // hint_itoa can NOT be reused here: it writes ANSI BYTES, while this",
    "  // buffer is UTF-16, and the mismatch shifted every following character",
    "  // into the high half of the previous code unit -- which is how a",
    "  // capture produced a file literally named \"<dir>7\\u7400\\u7800\\u7400\".",
    "  mov eax, [HINT_WANT]",
    "  test eax, eax",
    "  jnz hint_cp_num",
    "  mov eax, 1",                      # stage unknown -> fall back to 1.txt
    "hint_cp_num:",
    "  cmp eax, 9",
    "  jbe hint_cp_digit",
    "  mov eax, 1",
    "hint_cp_digit:",
    "  add eax, 30",                     # '0'
    "  mov [edi], ax",                   # UTF-16 code unit, high byte 0",
    "  add edi, 2",
    "  mov word ptr [edi], 2E",          # '.'
    "  mov word ptr [edi+2], 74",        # 't'
    "  mov word ptr [edi+4], 78",        # 'x'
    "  mov word ptr [edi+6], 74",        # 't'
    "  add edi, 8",
    "  mov word ptr [edi], 0",
    "hint_cp_done:",
    "  popad",
    "  ret",
    "",
    "hint_capture:",
    "  pushfd",
    "  pushad",
    "  mov dword ptr [HINT_CAP_OK], 0",
    "  // ---- the player's raw playfield position ----",
    "  mov eax, [DBG_PLAYER]",
    "  cmp eax, 10000",
    "  jb hint_capture_done",
    "  cmp eax, 7FFF0000",
    "  ja hint_capture_done",
    "  mov eax, [eax]",
    "  cmp eax, 10000",
    "  jb hint_capture_done",
    "  cmp eax, 7FFF0000",
    "  ja hint_capture_done",
    "  cvttss2si ecx, dword ptr [eax]",
    "  cvttss2si edx, dword ptr [eax+4]",
    "  mov [HINT_C_X], ecx",
    "  mov [HINT_C_Y], edx",
    "  // ---- the current stage frame ----",
    "  mov eax, [DBG_STAGE]",
    "  cmp eax, 10000",
    "  jb hint_capture_done",
    "  cmp eax, 7FFF0000",
    "  ja hint_capture_done",
    "  mov eax, [eax+4C]",
    "  mov [HINT_C_F], eax",
    "  call hint_chapter_end",
    "  // ---- choose the time form ----",
    "  // Inside a boss fight an absolute stage frame is useless for authoring a",
    "  // boss:P:F window: you cannot tell which pattern you are in, and the frame",
    "  // counter freezes through the dialogue.  So write the form the format",
    "  // actually wants -- boss:<current pattern>:<frames into it>, ending at",
    "  // boss:<next pattern>:0, i.e. \"until this pattern ends\".",
    "  mov dword ptr [HINT_C_KIND], 0",
    "  mov dword ptr [HINT_C_PID], 0",
    "  mov eax, [HINT_C_F]",
    "  mov [HINT_C_PF], eax",
    "  mov dword ptr [HINT_C_EKIND], 0",
    "  mov dword ptr [HINT_C_EPID], 0",
    "  mov eax, [HINT_CHAP_END]",
    "  mov [HINT_C_EF], eax",
    "  cmp dword ptr [HINT_PAT_ON], 0",
    "  je hint_cap_form_done",
    "  mov eax, [HINT_PAT_IDX]",
    "  mov dword ptr [HINT_C_KIND], 1",
    "  mov [HINT_C_PID], eax",
    "  mov ecx, [HINT_PAT_FRAME]",       # frames into this pattern (our clock)
    "  mov [HINT_C_PF], ecx",
    "  mov dword ptr [HINT_C_EKIND], 1",
    "  inc eax",
    "  mov [HINT_C_EPID], eax",
    "  mov dword ptr [HINT_C_EF], 0",
    "hint_cap_form_done:",
    "  // ---- build: \"+ 16 all <start> <x>,<y> <end>\" CRLF ----",
    "  mov edi, HINT_LINE",
    "  mov byte ptr [edi], 2B",
    "  mov byte ptr [edi+1], 20",
    "  add edi, 2",
    "  mov eax, [HINT_SIZE]",
    "  call hint_itoa",
    "  mov byte ptr [edi], 20",
    "  inc edi",
    "  mov byte ptr [edi], 61",
    "  mov byte ptr [edi+1], 6C",
    "  mov byte ptr [edi+2], 6C",
    "  mov byte ptr [edi+3], 20",
    "  add edi, 4",
    "  mov eax, [HINT_C_KIND]",
    "  mov ecx, [HINT_C_PID]",
    "  mov edx, [HINT_C_PF]",
    "  call hint_emit_time",
    "  mov byte ptr [edi], 20",
    "  inc edi",
    "  mov eax, [HINT_C_X]",
    "  call hint_itoa",
    "  mov byte ptr [edi], 2C",
    "  inc edi",
    "  mov eax, [HINT_C_Y]",
    "  call hint_itoa",
    "  mov byte ptr [edi], 20",
    "  inc edi",
    "  mov eax, [HINT_C_EKIND]",
    "  mov ecx, [HINT_C_EPID]",
    "  mov edx, [HINT_C_EF]",
    "  call hint_emit_time",
    "  mov byte ptr [edi], 0D",
    "  mov byte ptr [edi+1], 0A",
    "  add edi, 2",
    "  mov eax, HINT_LINE",
    "  sub edi, eax",
    "  mov [HINT_CAPLEN], edi",
    "  // ---- aim HINT_PATHW at <stage>.txt before opening ----",
    "  // load_hints leaves HINT_PATHW pointing at whichever file the directory",
    "  // walk happened to finish on, so appending straight to it dumped every",
    "  // capture into that one file -- which is exactly how a stage-7 capture",
    "  // ended up inside 1.txt.  Rebuild the name from the stage we resolved.",
    "  call hint_cap_path",
    "  // ---- open (creating if needed) and append ----",
    "  push 0",
    "  push 80",
    "  push 4",                          # OPEN_ALWAYS
    "  push 0",
    "  push 1",
    "  // GENERIC_READ | GENERIC_WRITE, not write-only: the tail check below",
    "  // has to READ the last byte, and a write-only handle makes ReadFile fail",
    "  // (ERROR_ACCESS_DENIED).  That failure is silent but not harmless -- the",
    "  // file pointer never advances, so the following write lands ON the last",
    "  // byte instead of after it.  It cost us a real character: a file ending",
    "  // \"...boss:3:0\" came back as \"...boss:3:\".",
    "  push C0000000",
    "  push HINT_PATHW",
    "  call dword ptr [FILE_IAT]",
    "  cmp eax, ffffffff",
    "  je hint_capture_done",
    "  mov [HINT_HANDLE], eax",
    "  // A brand new file needs its stage header first.",
    "  push 0",
    "  push eax",
    "  call dword ptr [GETSIZE_IAT]",
    "  test eax, eax",
    "  jnz hint_cap_ensure_nl",
    "  mov edi, HINT_LINE2",
    "  mov eax, [HINT_WANT]",
    "  call hint_itoa",
    "  mov byte ptr [edi], 0D",
    "  mov byte ptr [edi+1], 0A",
    "  add edi, 2",
    "  mov eax, HINT_LINE2",
    "  sub edi, eax",
    "  mov [HINT_CAPLEN2], edi",
    "  push 0",
    "  push HINT_WROTE",
    "  push dword ptr [HINT_CAPLEN2]",
    "  push HINT_LINE2",
    "  push dword ptr [HINT_HANDLE]",
    "  call dword ptr [WRITE_IAT]",
    "  jmp hint_capture_seek",
    "hint_cap_ensure_nl:",
    "  // The file already has content.  Make sure it ends with a line break",
    "  // BEFORE appending.  A file whose last line has no newline would have our",
    "  // entry glued onto it -- and that is not merely ugly: the tokens that end",
    "  // up after the merge get parsed as a stage header, so the rest of the",
    "  // file is misread (a real report: \"boss:1:0+ 16 all boss:3:1 ...\" made",
    "  // the parser take 16 for a stage number).",
    "  mov ecx, eax",                     # eax = the file size",
    "  dec ecx",                          # offset of the last byte
    "  push 0",                          # FILE_BEGIN
    "  push 0",                          # lpDistanceToMoveHigh = NULL
    "  push ecx",
    "  push dword ptr [HINT_HANDLE]",
    "  call dword ptr [SEEK_IAT]",
    "  push 0",
    "  push HINT_GOT",
    "  push 1",
    "  push HINT_LASTCH",
    "  push dword ptr [HINT_HANDLE]",
    "  call dword ptr [READ_IAT]",
    "  cmp byte ptr [HINT_LASTCH], 0A",   # already ends with a newline?
    "  je hint_capture_seek",
    "  // Terminate the last line first -- but seek to the END explicitly rather",
    "  // than trusting where the read left us.  If that read ever fails again,",
    "  // writing at the stale position would overwrite the file's last byte.",
    "  push 2",                          # FILE_END
    "  push 0",
    "  push 0",
    "  push dword ptr [HINT_HANDLE]",
    "  call dword ptr [SEEK_IAT]",
    "  mov byte ptr [HINT_LASTCH], 0D",   # no -> terminate the last line first
    "  mov byte ptr [HINT_LASTCH+1], 0A",
    "  push 0",
    "  push HINT_WROTE",
    "  push 2",
    "  push HINT_LASTCH",
    "  push dword ptr [HINT_HANDLE]",
    "  call dword ptr [WRITE_IAT]",
    "hint_capture_seek:",
    "  push 2",                          # FILE_END
    "  push 0",
    "  push 0",
    "  push dword ptr [HINT_HANDLE]",
    "  call dword ptr [SEEK_IAT]",
    "  push 0",
    "  push HINT_WROTE",
    "  push dword ptr [HINT_CAPLEN]",
    "  push HINT_LINE",
    "  push dword ptr [HINT_HANDLE]",
    "  call dword ptr [WRITE_IAT]",
    "  mov dword ptr [HINT_CAP_OK], 1",
    "  push dword ptr [HINT_HANDLE]",
    "  call dword ptr [CLOSE_IAT]",
    "hint_capture_done:",
    "  popad",
    "  popfd",
    "  ret",
    "",
])

# The RNG is a Mersenne Twister.  The game computes a 32-bit seed from the
# system clock, stores it in a global, and re-seeds the MT from that global
# when the *stage scene object is constructed* -- i.e. at the start of every
# stage, not just once per run.  The global is read in exactly one place
# (game+B2BD0) and the seeding wrapper has exactly one caller (game+B2BD9),
# which makes this the one clean interception point.
#
# Vanilla code at game+B2BD9:
#     mov eax, [SEED_GLOBAL]      ; 0xB2BD0
#     push eax                    ; 0xB2BD5
#     mov [edi+0x3C], eax         ; 0xB2BD6  the seed recorded in the run object
#     call 0xD04D0                ; 0xB2BD9  seed_wrapper -> seed()
# so on entry to our hook [esp] = return address and [esp+4] = the pushed seed,
# and we can simply rewrite [esp+4].
#
# The MT state immediately after seeding is a deterministic function of the
# seed, so we also fingerprint it (16 dwords).  That is what turns "same seed
# => same RNG" from a claim into something an external tool can check.
#
# v0.7.9 -- FIX: the hook used to read the argument as [esp+28].  Every literal
# in a .cea is HEX, so that is 0x28 = 40 bytes, but after pushfd + 5 pushes the
# argument is only 24 + 4 = 28 bytes up, i.e. [esp+1C].  The hook therefore read
# the stale dword 12 bytes above the argument and seeded the RNG with that
# whenever the seed lock was OFF -- which is the default.  Replay playback then
# diverges from the recording (boss non-spells come out differently and the
# replay eventually desyncs).  Keep this at 1C.
SEED_CODE = "\n".join([
    "\n// ---- seed lock ------------------------------------------------------ //",
    "// Entered via `call` from game+B2BD9.  On entry [esp] = return address and",
    "// [esp+4] = the seed the game pushed.  We deliberately do NOT rewrite that",
    "// stack slot: we push our own value for the wrapper call instead, so the",
    "// caller's frame is never touched (the game's own `add esp,4` at 0xB2BDE",
    "// still pops its stale argument).",
    "//",
    "// Registers are saved one at a time rather than with pushad, because we",
    "// need the caller's EDI *live* for the [edi+0x3C] write -- reading it out",
    "// of a pushad slot means depending on the slot order, and getting that",
    "// wrong writes the seed to an arbitrary address.",
    "//",
    "// NOTE every literal is HEX.  pushfd plus the five pushes below cover",
    "// 6*4 = 24 bytes, so the game's argument -- at [esp+4] on entry -- ends up",
    "// at [esp+1C] (that is 28 DECIMAL).  Writing `28` means 0x28 = 40 and reads",
    "// the stale dword 12 bytes ABOVE the argument, seeding the RNG with",
    "// something that is NOT the game's seed; that silently breaks replay",
    "// determinism because the recording used the real seed.  Keep it 1C.",
    "seed_hook:",
    "  pushfd",
    "  push eax",
    "  push ecx",
    "  push edx",
    "  push esi",
    "  push edi",
    "  mov eax, [esp+1C]",             # 0x1C = 28 decimal = the pushed seed
    "  cmp dword ptr [SEED_ON], 0",
    "  je seed_hook_used",
    "  mov eax, [SEL_SEED]",
    "  mov dword ptr [edi+3C], eax",   # edi is untouched, so this is the run object
    "  inc dword ptr [PRB_SEEDON]",
    "seed_hook_used:",
    "  mov [SEED_USED], eax",
    "  inc dword ptr [PRB_SEEDN]",
    "  push eax",                      # our value, not the caller's
    "  call game+D04D0",               # the original seed wrapper
    "  add esp, 4",
    "  // fingerprint the freshly seeded MT state (VA 0xEC8A90)",
    "  mov esi, EC8A90",
    "  mov edi, SEED_FP",
    "  mov ecx, 10",                   # 0x10 = 16 dwords; must match SEED_FP's size
    "seed_fp_loop:",
    "  mov eax, [esi]",
    "  mov [edi], eax",
    "  add esi, 4",
    "  add edi, 4",
    "  dec ecx",
    "  jnz seed_fp_loop",
    "  pop edi",
    "  pop esi",
    "  pop edx",
    "  pop ecx",
    "  pop eax",
    "  popfd",
    "  xor eax, eax",                  # the vanilla wrapper returns 0; keep it so
    "  ret",
    "",                                # the block must end on a newline: it is
])                                     # concatenated straight onto the next label

# Guard the code blocks before they get concatenated.  A stray comma at the end
# of a line inside one of the parenthesised "\n".join([...]) literals silently
# turns that whole constant into a TUPLE -- the file still parses, and the
# failure only shows up later as "can only concatenate str (not tuple) to str",
# or worse as a mangled build.  Cheaper to catch it here.
for _name, _val in (("OVERLAY_CODE", OVERLAY_CODE), ("SEED_CODE", SEED_CODE),
                    ("HINT_CODE", HINT_CODE), ("HINT_PARSE", HINT_PARSE),
                    ("HINT_CAPTURE", HINT_CAPTURE)):
    if not isinstance(_val, str):
        raise SystemExit("%s is a %s, not a string -- a stray comma inside its "
                         "string list turned it into a tuple"
                         % (_name, type(_val).__name__))
# Those blocks are built by IMPLICIT string concatenation inside bare
# parentheses, so every piece must end with a newline.  A piece that does not
# glues itself onto the next one -- and when the next one is CODE, that code
# ends up inside the preceding "//" comment and silently vanishes, with no
# syntax error anywhere to warn you.  Concatenation destroys the evidence, so
# this has to be checked against the SOURCE, not the assembled value.
def _audit_piece_newlines(path, names):
    """Every literal line of those blocks must end with \\n.

    Checked TEXTUALLY, not via the AST: implicit concatenation collapses the
    whole block into a single Constant, so the individual pieces are no longer
    visible once parsed.
    """
    import ast as _ast
    import re as _re
    src = open(path, encoding="utf-8").read()
    lines = src.split("\n")
    ranges = []
    for node in _ast.parse(src).body:
        if isinstance(node, _ast.Assign) and \
                any(getattr(t, "id", "") in names for t in node.targets):
            ranges.append((node.lineno, node.end_lineno))
    bad = []
    for lo, hi in ranges:
        for i in range(lo, hi):                     # hi is the closing ")"
            m = _re.match(r'^(\s*)"(.*)"\s*$', lines[i])
            if not m:
                continue
            body = m.group(2)
            if body.endswith("\\n") or body.endswith("\\r\\n"):
                continue
            if body == "":
                continue                            # a deliberate blank piece
            bad.append((i + 1, body[:60]))
    return bad


# ONLY OVERLAY_CODE: it is the one block built by implicit concatenation
# inside bare parentheses.  The others are "\n".join([...]) lists, where a
# missing \n is harmless because the join inserts one anyway -- and where a
# trailing comma is likewise harmless.  Auditing them would only produce noise.
_bad_pieces = _audit_piece_newlines(__file__, {"OVERLAY_CODE"})
if _bad_pieces:
    raise SystemExit(
        "asm string literal(s) missing a trailing \\n -- the following line "
        "would be swallowed by the preceding comment:\n  "
        + "\n  ".join("line %d: %r" % (l, s) for l, s in _bad_pieces))

# =========================================================================== #
# Settings file (v0.7.8)                                                      #
#   <exe dir>\prac.cfg -- plain text, one "key=value" per line.               #
#                                                                             #
#   Only "playerplus" is persisted today.  The reader scans the whole buffer  #
#   for the literal key, so more keys can be added without touching it.       #
#                                                                             #
#   Why: the Player+ cross is a read-out some people want and some do not, and  #
#   a build-time default cannot please both.  The F12 row is the default, and   #
#   any change to it is written straight back, so turning it off once keeps it   #
#   off until you turn it back on.  Deleting prac.cfg restores the default.      #
# =========================================================================== #
CFG_CODE = "\n".join([
    "// ---- cfg_path: CFG_PATHW = \"<exe dir>prac.cfg\" ------------------",
    "cfg_path:",
    "  pushad",
    "  push 104",
    "  push CFG_PATHW",
    "  push 0",
    "  call dword ptr [MODULE_IAT]      // GetModuleFileNameW",
    "  test eax, eax",
    "  jz cfg_path_done",
    "  mov esi, CFG_PATHW",
    "  lea edi, [esi+eax*2]",
    "cfg_path_cut:",
    "  cmp edi, esi",
    "  jbe cfg_path_done",
    "  sub edi, 2",
    "  cmp word ptr [edi], 5C           // backslash",
    "  jne cfg_path_cut",
    "  add edi, 2",
    "  mov esi, CFG_TAILW",
    "cfg_path_cp:",
    "  mov ax, [esi]",
    "  mov [edi], ax",
    "  add esi, 2",
    "  add edi, 2",
    "  test ax, ax",
    "  jnz cfg_path_cp",
    "cfg_path_done:",
    "  popad",
    "  ret",
    "",
    "// ---- cfg_load: read the file once and apply playerplus -------------",
    "// A missing file, a short file, or no matching key all leave the build's",
    "// own default alone, so a fresh install behaves exactly as before.",
    "cfg_load:",
    "  pushfd",
    "  pushad",
    "  mov dword ptr [CFG_LOADED], 1",
    "  mov eax, [OVL_V_PCROSS]",
    "  and eax, 1",
    "  mov [CFG_LAST], eax",
    "  call cfg_path",
    "  push 0",
    "  push 80                          // FILE_ATTRIBUTE_NORMAL",
    "  push 3                           // OPEN_EXISTING",
    "  push 0",
    "  push 1                           // FILE_SHARE_READ",
    "  push 80000000                    // GENERIC_READ",
    "  push CFG_PATHW",
    "  call dword ptr [FILE_IAT]        // CreateFileW",
    "  cmp eax, -1",
    "  je cfg_load_done",
    "  mov [CFG_H], eax",
    "  push 0",
    "  push CFG_RD",
    "  push 80                          // 128 bytes",
    "  push CFG_BUF",
    "  push dword ptr [CFG_H]",
    "  call dword ptr [READ_IAT]        // ReadFile",
    "  push dword ptr [CFG_H]",
    "  call dword ptr [CLOSE_IAT]       // CloseHandle",
    "  mov eax, [CFG_RD]",
    "  cmp eax, 80",
    "  jb cfg_len_ok",
    "  mov eax, 80",
    "cfg_len_ok:",
    "  mov [CFG_LEN], eax",
    "  mov esi, CFG_BUF",
    "  mov ecx, eax",
    "cfg_scan:",
    "  cmp ecx, 0B                      // the key is 11 bytes",
    "  jb cfg_load_done",
    "  push ecx",
    "  push esi",
    "  mov edi, CFG_KEY",
    "  mov edx, 0B",
    "cfg_cmp:",
    "  mov al, [esi]",
    "  or al, 20                        // case-fold; digits and '=' have bit 5",
    "  cmp al, [edi]",
    "  jne cfg_cmp_no",
    "  inc esi",
    "  inc edi",
    "  dec edx",
    "  jnz cfg_cmp",
    "  pop esi",
    "  pop ecx",
    "  movzx eax, byte ptr [esi+0B]",
    "  sub eax, 30",
    "  cmp eax, 1",
    "  jbe cfg_apply",
    "  xor eax, eax",
    "cfg_apply:",
    "  mov [OVL_V_PCROSS], eax",
    "  mov [CFG_LAST], eax",
    "  jmp cfg_load_done",
    "cfg_cmp_no:",
    "  pop esi",
    "  pop ecx",
    "  inc esi",
    "  dec ecx",
    "  jmp cfg_scan",
    "cfg_load_done:",
    "  popad",
    "  popfd",
    "  ret",
    "",
    "// ---- cfg_save: rewrite the file with the current value -------------",
    "cfg_save:",
    "  pushfd",
    "  pushad",
    "  mov eax, [OVL_V_PCROSS]",
    "  and eax, 1",
    "  mov [CFG_LAST], eax",
    "  mov [CFG_VAL], eax",
    "  call cfg_path",
    "  push 0",
    "  push 80",
    "  push 2                           // CREATE_ALWAYS",
    "  push 0",
    "  push 1",
    "  push 40000000                    // GENERIC_WRITE",
    "  push CFG_PATHW",
    "  call dword ptr [FILE_IAT]        // CreateFileW",
    "  cmp eax, -1",
    "  je cfg_save_done",
    "  mov [CFG_H], eax",
    "  mov esi, CFG_KEY",
    "  mov edi, CFG_LINE",
    "  mov ecx, 0B",
    "cfg_save_cp:",
    "  mov al, [esi]",
    "  mov [edi], al",
    "  inc esi",
    "  inc edi",
    "  dec ecx",
    "  jnz cfg_save_cp",
    "  mov eax, [CFG_VAL]",
    "  add eax, 30",
    "  mov [edi], al",
    "  inc edi",
    "  mov byte ptr [edi], 0A",
    "  inc edi",
    "  mov eax, CFG_LINE",
    "  sub edi, eax",
    "  push 0",
    "  push CFG_WROTE",
    "  push edi",
    "  push CFG_LINE",
    "  push dword ptr [CFG_H]",
    "  call dword ptr [WRITE_IAT]       // WriteFile",
    "  push dword ptr [CFG_H]",
    "  call dword ptr [CLOSE_IAT]       // CloseHandle",
    "cfg_save_done:",
    "  popad",
    "  popfd",
    "  ret",
    "",
    "// ---- cfg_tick: once per frame, from overlay_logic ------------------",
    "// Load on the first frame; after that write back only when the value the",
    "// menu holds stops matching what we last persisted.",
    "cfg_tick:",
    "  cmp dword ptr [CFG_LOADED], 0",
    "  jne cfg_tick_chk",
    "  call cfg_load",
    "  ret",
    "cfg_tick_chk:",
    "  mov eax, [OVL_V_PCROSS]",
    "  and eax, 1",
    "  cmp eax, [CFG_LAST]",
    "  je cfg_tick_done",
    "  call cfg_save",
    "cfg_tick_done:",
    "  ret",
    "",
])

CFG_DATA = "\n".join([
    "// ================= settings file data (v0.7.8) ====================",
    "CFG_TAILW:",
    # "prac.cfg" as UTF-16LE + NUL, spelled out because _utf16() is defined
    # further down the file (after the block that consumes CFG_DATA).
    "  db 70 00 72 00 61 00 63 00 2E 00 63 00 66 00 67 00 00 00",
    "CFG_KEY:",
    "  db " + " ".join("%02X" % ord(c) for c in "playerplus="),
    "CFG_PATHW:",
    "\n".join(["  db " + " ".join(["00"] * 16)] * 32
              + ["  db 00 00 00 00 00 00 00 00"]),          # 520 bytes = MAX_PATH WCHARs
    "CFG_BUF:",
    "\n".join(["  db " + " ".join(["00"] * 16)] * 8),      # 128 bytes, the file is 13
    "CFG_LINE:",
    "  db 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
    "CFG_H:",
    "  dd 0",
    "CFG_RD:",
    "  dd 0",
    "CFG_LEN:",
    "  dd 0",
    "CFG_VAL:",
    "  dd 0",
    "CFG_LOADED:",
    "  dd 0",
    "// -1 so the very first cfg_tick_chk cannot match by accident.",
    "CFG_LAST:",
    "  dd FFFFFFFF",
    "CFG_WROTE:",
    "  dd 0",
    "",
])


sub(
    "overlay",
    "cave:\ncustomMenuRender:\n",
    "// --- F12 overlay (v0.4.0): eight in-place patches --------------------- //\n"
    "// game+CFFCD is 10 bytes into the real per-frame function.\n"
    "game+CFFCD:\n"
    " jmp overlay_entry\n"
    " nop\n"
    " nop\n"
    " nop\n"
    " nop\n"
    " nop\n"
    "game+CFFD7:\n"
    "// the present function's entry (9 bytes: push ebp / mov ebp,esp /\n"
    "// sub esp,0x4cc).  Everything the game draws for this frame is already\n"
    "// in the surface; nothing has been blitted yet.\n"
    "game+14BD50:\n"
    " jmp overlay_present\n"
    " nop\n"
    " nop\n"
    " nop\n"
    " nop\n"
    "game+14BD59:\n"
    "// the four keyboard-refresh sites, each `call game+140CD0` (5 bytes).\n"
    "game+CF255:\n"
    " call overlay_input\n"
    "game+CF25A:\n"
    "game+CF2B5:\n"
    " call overlay_input\n"
    "game+CF2BA:\n"
    "game+CF445:\n"
    " call overlay_input\n"
    "game+CF44A:\n"
    "game+CF7CD:\n"
    " call overlay_input\n"
    "game+CF7D2:\n"
    "// ---- v0.4.0: the game-over decision (6 bytes) ----\n"
    "// `cmp [player+0x48],0 / jg respawn` -- when the comparison would say\n"
    "// \"no lives left\" and No Gameover is on, we hand the game a life of 1\n"
    "// so the shared `dec` lands on 0 instead of the GAME OVER branch.\n"
    "game+B980C:\n"
    " jmp nogameover_hook\n"
    " nop\n"
    "game+B9812:\n"
    "// ---- v0.4.0: freeze power (33 bytes); v0.4.2 locks onto the live value ----\n"
    "// The whole vanilla `clamp power into [0,500]` block.  It already runs\n"
    "// once per frame, so taking it over costs no extra work.\n"
    "game+B9B05:\n"
    " jmp ovl_lockpower\n"
    + " nop\n" * 28 +
    "game+B9B26:\n"
    "// ---- v0.5.0: the RNG seed (5 bytes) ----\n"
    "// The single call to the seed wrapper.  When SEED_ON is 0 the hook just\n"
    "// forwards the game's own argument, so this is byte-equivalent to vanilla.\n"
    "game+B2BD9:\n"
    " call seed_hook\n"
    "game+B2BDE:\n"
    "cave:\n"
    + OVERLAY_CODE + SEED_CODE + HINT_CODE + HINT_PARSE + HINT_CAPTURE + CFG_CODE +
    "customMenuRender:\n",
    "hook the per-frame function and add the overlay payload",
)


def _utf16(s):
    """A NUL-terminated UTF-16LE byte list, as `db` tokens."""
    out = []
    for ch in s:
        out.append("%02X" % (ord(ch) & 0xFF))
        out.append("%02X" % (ord(ch) >> 8))
    return " ".join(out + ["00", "00"])



OVERLAY_DATA = "\n".join([
    "// ---- F12 overlay (v0.4.0) state ----",
    "OVERLAY_OPEN:",
    "  dd 0",
    "OVL_DRAWN:",
    "  dd 0",
    "OVL_CUR:",
    "  dd 0",
    "OVL_ROWS_N:",
    "  dd C",                                  # 12 rows: 11 + Player + (v0.7.7)
    "OVL_PREV_F12:",
    "  db 0",
    "// One byte per key whose rising edge we care about: UP, DOWN, LEFT, RIGHT,",
    "// then Z (5A), ESC (1B), BACK (08).  Cleared with two dword stores.",
    "OVL_PREV_KEYS:",
    "  db 0 0 0 0 0 0 0 0",
    "OVL_VKBUF:",
    "  db " + " ".join(["00"] * 256),
    "",
    "// ---- Seed row digit entry (v0.5.1) ---------------------------------",
    "// OVL_TYPE_LAST is the VK of the digit currently held, which gives rising",
    "// edge detection for all ten digits with a single word.",
    "OVL_TYPE_ON:",
    "  dd 0",
    "OVL_TYPE_OLD:",
    "  dd 0            // value to restore if you press ESC",
    "OVL_TYPE_FRESH:",
    "  dd 0            // 1 -> the next digit replaces instead of appending",
    "OVL_TYPE_LAST:",
    "  dd 0",
    "// Which row is in typing mode, so its label can be restored without\n"
    "// hard-coding a row index (see ovl_type_toggle).",
    "OVL_TYPE_ROW:",
    "  dd 0",
    "OVL_PREV_SEEDSW:",
    "  dd 0            // previous SEED_ON, for the grab-on-rising-edge",
    "// Row-draw cursor.  Kept in memory because the game's text helpers do not",
    "// preserve registers across calls (see the row loop).",
    "OVL_RCUR:",
    "  dd 0",
    "OVL_RPTR:",
    "  dd 0",
    "OVL_RY:",
    "  dd 0",
    "// The label the row loop decided to draw this iteration (its own format, or",
    "// an on/off string from OVL_ALT).  Both the shadow and the real pass use it,",
    "// so it is computed once per row.",
    "OVL_RTXT:",
    "  dd 0",
    "",
    "// ---- held-key fine adjustment (v0.4.1) -----------------------------",
    "// Holding LEFT/RIGHT first repeats the row's own step, and after",
    "// OVL_HOLD_DELAY frames it switches to +-1 every OVL_NUDGE_EVERY frames.",
    "// Without this a 0..500 row (Power) or a 0..65535 row (Seed) cannot be",
    "// set to a chosen value.",
    "OVL_HOLD_DIR:",
    "  dd 0            // 0 = neither, 1 = RIGHT, 2 = LEFT",
    "OVL_HOLD_N:",
    "  dd 0            // frames the current direction has been held",
    "OVL_NUDGE_N:",
    "  dd 0            // frames since the last +-1",
    "OVL_HOLD_DELAY:",
    "  dd 14           // 0x14 = 20 frames ~ 0.33 s before the fine step starts",
    "OVL_NUDGE_EVERY:",
    "  dd 3            // then one +-1 every 3 frames ~ 20/s",
    "",
    "// ---- seed lock (v0.5.0) -------------------------------------------",
    "// SEED_ON = 0 -> the hook forwards the game's own time-based seed, i.e.",
    "//                the behaviour is identical to vanilla.",
    "// SEED_ON = 1 -> the seed is forced to SEL_SEED.",
    "SEED_ON:",
    "  dd 0",
    "SEL_SEED:",
    "  dd 0",
    "// What was actually used, and a fingerprint of the MT state right after",
    "// seeding.  Same seed => same fingerprint, which is the whole proof.",
    "SEED_USED:",
    "  dd 0",
    "SEED_FP:",
    "  dd " + " ".join(["0"] * 16),
    "",
    "// row = text, value pointer, min, max, step, wrap",
    "//   wrap = 1 -> stepping past an end jumps to the other end (a switch)",
    "//          0 -> stepping past an end stops there (a wide range)",
    "//   Hint rows sit above the seed rows (v0.6.0): hint is the higher-value",
    "//   feature, so it gets the top of the menu.",
    "//   row 1  No Gameover -- the 不疮 switch, read by nogameover_hook",
    "//   row 2  Lock Power  -- read by ovl_lockpower, which locks onto the",
    "//                        power you have at the moment you turn it on",
    "//   row 3  Hint        -- master switch for the hint markers",
    "//   row 4  Capture     -- write the player's current spot into hint/*.txt",
    "//   row 5  Frame       -- read-only: the stage frame counter",
    "//   row 6  Lock Seed   -- this IS SEED_ON: turning it on grabs the seed",
    "//                        the current run is using into row 7",
    "//   row 7  Seed        -- this IS SEL_SEED, used by seed_hook when row 6",
    "//                        is on.  Z types digits; the step is only a coarse",
    "//                        nudge, because 4294967295 is ten digits long.",
    "//   row 8  Hit         -- read-only: how many times you have been hit",
    "//   (the old row 11, Freeze, is gone: it never worked and the user asked",
    "//    for it to be dropped -- see plan-hint.md 19)",
    "OVL_ROWS:",
    "  dd TXT_OVL_NOGAMEOVER, OVL_V_NOGAMEOVER, 0, 1,        1,       1",
    "  dd TXT_OVL_LOCKPWR,    OVL_V_LOCKPWR,    0, 1,        1,       1",
    "  dd TXT_OVL_HINT,       OVL_V_HINT,       0, 1,        1,       1",
    "  // v0.7.7  Player + -- the self-machine judgement-point cross, ported",
    "  //                     from le03.  It is gated by its OWN switch, not",
    "  //                     by Hint, and it is drawn from the same playfield",
    "  //                     position through the same Fix/ORIGIN transform as",
    "  //                     the hint markers, so the two always agree.",
    "  dd TXT_OVL_PCROSS,     OVL_V_PCROSS,     0, 1,        1,       1",
    "  dd TXT_OVL_CAPTURE,    OVL_V_CAPTURE,    0, 0,        0,       0",
    "  dd TXT_OVL_FRAME,      OVL_V_FRAME,      0, 0,        0,       0",
    "  // row 6  Pattern -- read-only: which boss pattern is running.  It is the\n"
    "  //                     game's own 0-based \"Pattern number\" (0 = the first\n"
    "  //                     pattern of the stage = the mid non-spell), which is\n"
    "  //                     exactly what boss:P:F takes.  -1 means \"no pattern\"\n"
    "  //                     (mid-stage, or no trustworthy number).\n"
    "  dd TXT_OVL_PATTERN,    OVL_V_PATTERN,   0, 0,        0,       0",
    "  dd TXT_OVL_LOCKSEED,   SEED_ON,          0, 1,        1,       1",
    "  dd TXT_OVL_SEED,       SEL_SEED,         0, FFFFFFFF, 1000000, 0",
    "  dd TXT_OVL_DEBT,       OVL_V_DEBT,       0, 0,        0,       0",
    "  dd TXT_OVL_FIX_X,      HINT_DX,         0, 80,       1,       0",
    "  dd TXT_OVL_FIX_Y,      HINT_DY,         0, 80,       1,       0",
    "",
    "// Parallel to OVL_ROWS, one dword per row, in the same order.",
    "//   0                -> the row draws its own format string (a number)",
    "//   &{off,on} pair   -> the row draws that text instead, chosen by the",
    "//                       value, so a 0..1 switch reads off/on",
    "// Z flips any row whose range is exactly 0..1 (see ovl_type_toggle).",
    "OVL_ALT:",
    "  dd ALT_NOGAMEOVER",              # 0  No Gameover
    "  dd ALT_LOCKPWR",                 # 1  Lock Power
    "  dd ALT_HINT",                    # 2  Hint
    "  dd ALT_PCROSS",                  # 3  Player +
    "  dd 0",                           # 4  Capture   (a count)
    "  dd 0",                           # 5  Frame     (a number)
    "  dd 0",                           # 6  Pattern   (a number)
    "  dd ALT_LOCKSEED",                # 7  Lock Seed
    "  dd 0",                           # 8  Seed
    "  dd 0",                           # 9  Debt
    "  dd 0",                           # 10 Fix X
    "  dd 0",                           # 11 Fix Y
    "OVL_V_NOGAMEOVER:",
    "  dd 0",
    "OVL_V_LOCKPWR:",
    "  dd 0",
    "OVL_V_HINT:",
    "  // Defaults to ON: the cave's data is part of the section's raw bytes, so",
    "  // this is the value the process starts with -- hint markers are visible",
    "  // from the moment the game launches, and the F12 row is there to turn",
    "  // them off.  (Verified: HINT_OX/HINT_FADE_R/OVL_ROWS_N all load from",
    "  // these same bytes rather than starting zeroed.)",
    "  dd 1",
    "OVL_V_PCROSS:",
    "  // Defaults to ON, exactly like the le03 Player+ row.  It is a read-out",
    "  // of where the judgement point really is, so it is most useful left on;",
    "  // the F12 row is there to hide it again.",
    "  dd 1",
    "OVL_V_CAPTURE:",
    "  dd 0",
    "OVL_V_FRAME:",
    "  dd 0",
    "// Mirror of HINT_PAT_IDX for the read-only Pattern row.  Kept separate so",
    "// the menu shows what the HINT LOGIC is actually using, rather than a",
    "// second reading of the game that could disagree with it.",
    "OVL_V_PATTERN:",
    "  dd 0",
    "OVL_V_DEBT:",
    "  dd 0",
    "// ---- hint geometry (v0.6.0) -----------------------------------------",
    "// The playfield is 384 x 448 with float coordinates at [[player]+0], and",
    "// it sits at (31,16) in the same 640x480 panel space.  Measured, not",
    "// guessed: scanning the frame for the strongest vertical/horizontal edges",
    "// puts the playfield borders at panel x 31.0 and 415.7 (384.7 apart) and",
    "// panel y 15.6 and 464.7 (449.1 apart), and the player's own coordinates",
    "// then land exactly on the sprite (223.6 measured vs 223.0 predicted).",
    "// These are plain variables rather than immediates so they can be",
    "// re-calibrated from outside if a different resolution ever disagrees.",
    "HINT_OX:",
    "  dd 1F",
    "HINT_OY:",
    "  dd 10",
    "HINT_SIZE:",
    "  dd 10          // the marker arm length in pixels (0x10 = 16)",
    "HINT_CX:",
    "  dd 0           // scratch: the marker centre in panel space",
    "HINT_CY:",
    "  dd 0",
    "HINT_HALF:",
    "  dd 0",
    "// Raw playfield coordinates as the marker saw them, so HINT_OX/HINT_OY can",
    "// be solved for exactly by comparing these with a screenshot.",
    "DBG_PX:",
    "  dd 0",
    "DBG_PY:",
    "  dd 0",
    "DBG_STAGE:",
    "  dd 0           // [DBG_STAGE+0x4C] is the stage frame counter",
    "// The power Lock Power has latched onto, plus a one-shot so the capture",
    "// happens on exactly the first frame after the switch goes on.",
    "OVL_LP_TARGET:",
    "  dd 0",
    "OVL_LP_HELD:",
    "  dd 0",
    "// How many times the player has been hit THIS ATTEMPT.",
    "//",
    "// It was originally named for \"owed lives\", on the assumption that the",
    "// hook only runs on a FATAL hit.  It does not: game+B980C sits in the death",
    "// sequence (entered when [edi+0x24c] >= 0x14), which every hit runs through",
    "// -- including a deathbomb, where a bomb is used on the hit frame and no",
    "// life is actually lost.  So it is a hit counter, and the menu row says so.",
    "//",
    "// v0.7.5 -- it is now ZEROED at every stage start by the initFrameTimer",
    "// hook, so it counts hits for the attempt in front of you rather than",
    "// accumulating from launch.  That hook fires once per stage construction,",
    "// which includes every practice-mode retry.",
    "NOSORE_DEBT:",
    "  dd 0",
    "TXT_OVL_TITLE:",
    "  db " + _utf16("F12 MENU"),
    "TXT_OVL_NOGAMEOVER:",
    "  db " + _utf16("No Gameover: %d"),
    "TXT_OVL_LOCKPWR:",
    "  db " + _utf16("Lock Power:  %d"),
    "TXT_OVL_HINT:",
    "  db " + _utf16("Hint:        %d"),
    "TXT_OVL_PCROSS:",
    "  db " + _utf16("Player +:    %d"),
    "TXT_OVL_CAPTURE:",
    "  db " + _utf16("Capture:     %d"),
    "TXT_OVL_FRAME:",
    "  db " + _utf16("Frame:       %d"),
    "TXT_OVL_PATTERN:",
    "  db " + _utf16("Pattern:     %d"),
    "TXT_OVL_LOCKSEED:",
    "  db " + _utf16("Lock Seed:   %d"),
    "TXT_OVL_SEED:",
    "  db " + _utf16("Seed:        %u"),
    "TXT_OVL_SEED_EDIT:",
    "  db " + _utf16("Seed[type]:  %u"),
    "TXT_OVL_DEBT:",
    "  db " + _utf16("Hit:         %d"),
    "TXT_OVL_FIX_X:",
    "  db " + _utf16("Fix X:       %d"),
    "TXT_OVL_FIX_Y:",
    "  db " + _utf16("Fix Y:       %d"),
    "// ---- on/off labels for the 0..1 switch rows ----",
    "// Each ALT_* is a 2-dword table {text_if_0, text_if_1} pointed at by the",
    "// matching slot of OVL_ALT.  These strings carry no format specifier, so",
    "// the value argument the draw loop pushes is simply ignored.",
    "ALT_NOGAMEOVER:",
    "  dd TXT_NOGAMEOVER_OFF, TXT_NOGAMEOVER_ON",
    "ALT_LOCKPWR:",
    "  dd TXT_LOCKPWR_OFF, TXT_LOCKPWR_ON",
    "ALT_HINT:",
    "  dd TXT_HINT_OFF, TXT_HINT_ON",
    "ALT_PCROSS:",
    "  dd TXT_PCROSS_OFF, TXT_PCROSS_ON",
    "ALT_LOCKSEED:",
    "  dd TXT_LOCKSEED_OFF, TXT_LOCKSEED_ON",
    "TXT_NOGAMEOVER_OFF:",
    "  db " + _utf16("No Gameover: off"),
    "TXT_NOGAMEOVER_ON:",
    "  db " + _utf16("No Gameover: on "),
    "TXT_LOCKPWR_OFF:",
    "  db " + _utf16("Lock Power:  off"),
    "TXT_LOCKPWR_ON:",
    "  db " + _utf16("Lock Power:  on "),
    "TXT_HINT_OFF:",
    "  db " + _utf16("Hint:        off"),
    "TXT_HINT_ON:",
    "  db " + _utf16("Hint:        on "),
    "TXT_PCROSS_OFF:",
    "  db " + _utf16("Player +:    off"),
    "TXT_PCROSS_ON:",
    "  db " + _utf16("Player +:    on "),
    "TXT_LOCKSEED_OFF:",
    "  db " + _utf16("Lock Seed:   off"),
    "TXT_LOCKSEED_ON:",
    "  db " + _utf16("Lock Seed:   on "),
    "",
])

# Diagnostic counters at a *fixed* cave offset (cave+0x3000) so an external
# tool can poll them by absolute address without knowing the code layout.
PROBE_DATA = "\n".join([
    "// ---- F12 overlay (v0.4.0) diagnostic counters ----------------------",
    "// Polled by tools/probe.py with ReadProcessMemory.  They stay in the",
    "// shipped build: a few dozen bytes buys a remote answer to \"is the hook",
    "// running?\" without attaching a debugger.",
    "PRB_FRAMES:",
    "  dd 0",
    "PRB_INPUT:",
    "  dd 0",
    "PRB_BLIT:",
    "  dd 0",
    "PRB_F12:",
    "  dd 0",
    "PRB_F12N:",
    "  dd 0",
    "PRB_OPEN:",
    "  dd 0",
    "PRB_PRES:",
    "  dd 0",
    "// v0.4.0",
    "PRB_NOGAMEOVER:",
    "  dd 0",
    "PRB_LP:",
    "  dd 0",
    "// v0.5.0 -- seed lock",
    "PRB_SEEDN:",
    "  dd 0",
    "PRB_SEEDON:",
    "  dd 0",
    "PRB_SEEDVAL:",
    "  dd 0",
    "// Diagnostic mirror of the live player object, refreshed once per frame\n"
    "// by ovl_lockpower.  Read [DBG_PLAYER] to get the pointer; lives are at\n"
    "// +0x48, bombs +0x60, power +0x7C.",
    "DBG_PLAYER:",
    "  dd 0",
    "",
])

sub("overlay", "cave_end:\n",
    OVERLAY_DATA + "\n" + CFG_DATA + "\ncave+5000:\n" + PROBE_DATA + "\ncave_end:\n",
    "the overlay's state block + the settings-file buffers")

# ---- v0.6.0: hint file storage -------------------------------------------
# The cave is enlarged to 0x8000 for this; HINT_BUF gets the whole upper half
# (16 KB) and is only declared, not emitted -- the section is zero-filled.
HINT_DATA = "\n".join([
    "// ---- hint files (v0.6.0) ----",
    "// GetModuleFileNameW writes the exe path here; we chop it at the last",
    "// backslash and append \"hint\\<stage>.txt\".",
    "HINT_PATHW:",
    "  db " + " ".join(["00"] * 520),      # 260 WCHARs
    "HINT_PRE:",
    "  db " + _utf16("hint\\"),
    "HINT_GLOB:",
    "  db " + _utf16("*.txt"),
    "HINT_FIND:",
    "  db " + " ".join(["00"] * 592),
    "HINT_FH:",
    "  dd 0",
    "HINT_PRELEN:",
    "  dd 0",
    "HINT_OK:",
    "  dd 0",
    "HINT_SUF:",
    "  db " + _utf16(".txt"),
    "HINT_BUFMAX:",
    "  dd 1800",                          # 0x1800 = 6 KB of text
    "HINT_HANDLE:",
    "  dd 0",
    "HINT_GOT:",
    "  dd 0",
    "HINT_LEN:",
    "  dd 0",
    "// ---- marker shape and colour ----",
    "HINT_SYM:",
    "  dd 2B",                            # '+' ; 2D is '-'
    "HINT_COL:",
    "  dd FF",
    "HINT_COL_DIM:",
    "  dd 40",
    "HINT_FADE_R:",
    "  dd 28",        # 0x28 = 40 playfield px
    "// Marker correction, added to the marker's playfield coordinates.\n"
    "// BIASED by 0x40 because ovl_apply compares unsigned, so a row\n"
    "// cannot hold a negative number: 0x40 means no shift, 0x40+n moves\n"
    "// the marker n pixels right/down.  Menu rows Fix X / Fix Y expose\n"
    "// this so the marker can be dialled onto the game's own hitbox dot.\n"
    "HINT_DX:",
    "  dd 41",       # 0x41 = 65 = one pixel right of the raw position
    "HINT_DY:",
    "  dd 40",       # 0x40 = 64 = no vertical shift
    "HINT_DASH:",
    "  dd 10",                            # dash pitch (0x10 = 16)
    "HINT_USECOL:",
    "  dd 0",
    "HINT_DASHLEN:",
    "  dd 0",
    "HINT_DASHEND:",
    "  dd 0",
    "// ---- parser state (v0.6.3) ----",
    "HINT_P:",
    "  dd 0",
    "HINT_END:",
    "  dd 0",
    "HINT_CURSTAGE:",
    "  dd 0",
    "HINT_WANT:",
    "  dd 0",
    "HINT_N:",
    "  dd 0",
    "HINT_MAXN:",
    "  dd 18",
    "HINT_SKIP:",
    "  dd 0",
    "HINT_TOK:",
    "  db " + " ".join(["00"] * 40),
    "HINT_E_MARK:",
    "  dd 0",
    "HINT_E_SIZE:",
    "  dd 0",
    "HINT_E_CHAR:",
    "  dd 0",
    "HINT_E_X:",
    "  dd 0",
    "HINT_E_Y:",
    "  dd 0",
    "HINT_E_SK:",
    "  dd 0",
    "HINT_E_SP:",
    "  dd 0",
    "HINT_E_SF:",
    "  dd 0",
    "HINT_E_EK:",
    "  dd 0",
    "HINT_E_EP:",
    "  dd 0",
    "HINT_E_EF:",
    "  dd 0",
    "HINT_TKIND:",
    "  dd 0",
    "HINT_TPAT:",
    "  dd 0",
    "HINT_TFR:",
    "  dd 0",
    "HINT_CUR:",
    "  dd 0",
    "HINT_ROW:",
    "  dd 0",
    "// ---- capture state (v0.6.4) ----",
    "HINT_C_X:",
    "  dd 0",
    "HINT_C_Y:",
    "  dd 0",
    "HINT_C_F:",
    "  dd 0",
    "HINT_CHAP_END:",
    "  dd 0",
    "// ---- boss pattern state (v0.7.2) ----",
    "// HINT_PAT_IDX is the 0-BASED pattern ordinal the boss is on right now --",
    "// the very same number the hint file's boss:P:F uses: 0 midnon, 1 midspell,",
    "// 2 non1, 3 spell1, 4 non2, 5 spell2 ... for stage 1.  It is a straight",
    "// copy of the game's own [boss+0x44] (no offset -- see the evidence chain",
    "// in ovl_boss_poll) and is only meaningful while HINT_PAT_ON is 1.",
    "// HINT_PAT_FRAME counts frames into the pattern (our own clock).",
    "HINT_PAT_IDX:",
    "  dd 0",
    "// 1 only while a boss or mid-boss is on screen AND its pattern number is",
    "// trustworthy.  Pattern 0 is a real pattern (the mid non-spell), so \"no",
    "// pattern\" can never be spelled with a number -- it needs this flag (the",
    "// Pattern row renders ON=0 as -1).",
    "HINT_PAT_ON:",
    "  dd 0",
    "// Frames into the current pattern, counted by US (one per frame) rather",
    "// than as a delta on [stage+0x4C], which freezes during intro dialogue.",
    "HINT_PAT_FRAME:",
    "  dd 0",
    "// Was a boss on screen last frame?  A 0->1 edge means a new fight, whose",
    "// object is built carrying the previous fight's last pattern number.",
    "HINT_PAT_WAS:",
    "  dd 0",
    "// The last pattern actually accepted (FFFFFFFF = none yet), and the value",
    "// to ignore until the new fight's own first pattern starts.",
    "HINT_PAT_LAST:",
    "  dd FFFFFFFF",
    "HINT_PAT_SKIP:",
    "  dd FFFFFFFF",
    "// The time specs the capture is about to write (see hint_emit_time).",
    "HINT_C_KIND:",
    "  dd 0",
    "HINT_C_PID:",
    "  dd 0",
    "HINT_C_PF:",
    "  dd 0",
    "HINT_C_EKIND:",
    "  dd 0",
    "HINT_C_EPID:",
    "  dd 0",
    "HINT_C_EF:",
    "  dd 0",
    "HINT_IEDI:",
    "  dd 0",
    "HINT_CAPLEN:",
    "  dd 0",
    "HINT_CAPLEN2:",
    "  dd 0",
    "HINT_WROTE:",
    "  dd 0",
    "HINT_CAP_OK:",
    "  dd 0",
    "HINT_LINE:",
    "  db " + " ".join(["00"] * 48) + "\n"
    "HINT_LINE2:",
    "  db " + " ".join(["00"] * 8) + "\n"
    "// Scratch for the tail-of-file newline check: holds the file's last byte,\n"
    "// and is written back as CRLF when that byte is not already a newline.\n"
    "HINT_LASTCH:",
    "  db 00 00\n"
    "OVL_PREV_CAP:",
    "  dd 0",
    "",
])

sub("hint", "cave_end:\n",
    HINT_DATA + "cave_end:\n",
    "the hint file state")

# ---- v0.6.0: hint support -------------------------------------------------
# initFrameTimer is BAN's hook that initialises the stage frame counter, so it
# is the one place guaranteed to see the stage object (edi) at the start of
# every stage.  Stash it: [stage+0x4C] is the frame counter, and the hint
# scheduler needs both that and the object itself.
#
# It is called from game+B32C6, inside the stage-construction routine (the
# same one that resets the frame counters and loads the 25 stage resources),
# so it fires once per stage -- including every practice-mode RETRY, which
# builds a fresh stage object.  That makes it the correct "new attempt"
# boundary for anything that should be per-attempt.
sub(
    "hint",
    "initFrameTimer:\n"
    "\n"
    "  pushfd\n"
    "  push eax\n"
    "  mov dword ptr [edi+4C], 0\n",

    "initFrameTimer:\n"
    "\n"
    "  pushfd\n"
    "  push eax\n"
    "  mov [DBG_STAGE], edi\n"
    "  // load_hints already calls parse_hints once per file it enumerates,\n"
    "  // so there must NOT be a parse_hints call here as well: it would\n"
    "  // re-parse whatever text is still sitting in HINT_BUF (the last file\n"
    "  // read) and double-count that file's entries.\n"
    "  call load_hints\n"
    "  // v0.7.5 -- the Hit counter is per ATTEMPT, not per process.  It used\n"
    "  // to accumulate from launch forever, so a retry (or starting a new\n"
    "  // stage in a full run) inherited the previous attempt's total.  This\n"
    "  // hook is the one point guaranteed to run at every stage start, so\n"
    "  // zero it here.  (NOSORE_DEBT is the storage; the F12 row mirrors it\n"
    "  // into OVL_V_DEBT every frame, so the row follows automatically.)\n"
    "  mov dword ptr [NOSORE_DEBT], 0\n"
    "  mov dword ptr [edi+4C], 0\n",
    "stash the stage object for the frame counter and the hint scheduler",
)

sub(
    "overlay",
    "[DISABLE]\ngame+73F67:\n",
    "[DISABLE]\n"
    "game+CFFCD:\n"
    " db C7 05 10 51 A6 00 01 00 00 00\n"
    "game+14BD50:\n"
    " db 55 8B EC 81 EC CC 04 00 00\n"
    "game+CF255:\n"
    " db E8 76 1A 07 00\n"
    "game+CF2B5:\n"
    " db E8 16 1A 07 00\n"
    "game+CF445:\n"
    " db E8 86 18 07 00\n"
    "game+CF7CD:\n"
    " db E8 FE 14 07 00\n"
    "game+B980C:\n"
    " db 83 78 48 00 7F 2E\n"
    "game+B9B05:\n"
    " db 8B 07 83 78 7C 00 7D 07 C7 40 7C 00 00 00 00 8B 07 81 78 7C F4 01 00 00 7C 07 C7 40 7C F4 01 00 00\n"
    "game+B2BD9:\n"
    " db E8 F2 D8 01 00\n"
    "game+73F67:\n",
    "restore bytes for the overlay hook sites",
)


def data_block():
    lines = ["SECTION_CNT:", " db 7 6 8 8 9 5 A", "SECTION_TABLE:"]
    for i in range(7):
        lines.append(" dd sec_%d" % i)
    for i in range(7):
        lines.append("sec_%d:" % i)
        frames = SECTIONS[i] or [0]
        lines.append("  dd " + " ".join("%X" % f for f in frames))
    lines += [
        "MODE_TXTS:", " dd mode_0", " dd mode_1",
        "mode_0:", "  db 42 00 6f 00 73 00 73 00 00 00",                    # "Boss"
        "mode_1:", "  db 53 00 65 00 63 00 74 00 69 00 6f 00 6e 00 00 00",  # "Section"
        "TXT_MODE:", "  db 4d 00 6f 00 64 00 65 00 3a 00 20 00 25 00 73 00 00 00",
        "TXT_SECTION:",
        "  db 53 00 65 00 63 00 74 00 69 00 6f 00 6e 00 3a 00 20 00 25 00 64 00 00 00",
        "TXT_LIFE:",
        "  db 4c 00 69 00 66 00 65 00 3a 00 20 00 25 00 64 00 00 00",
        "TXT_BOMB:",
        "  db 42 00 6f 00 6d 00 62 00 3a 00 20 00 25 00 64 00 00 00",
        "",
        "// Per-character default bombs, in the game's own character order.",
        "BOMB_DEF:",
        "  dd 4 2 3 5",
        "LAST_CHAR:",
        "  dd ffffffff",
        "",
        "// Wrap dwell state (see wrap_latch).",
        "WRAP_LOCK:",
        "  dd 0",
        "WRAP_TIMER:",
        "  dd 0",
        "",
    ]
    return "\n".join(lines)


sub("moderow", "cave_end:\n", data_block() + "cave_end:\n", "chapter tables + mode strings")

# HINT_BUF is only *declared*, so it emits no bytes -- which means whatever data
# block comes next lands right on top of it.  It therefore has to be reserved
# AFTER every other data block, not where it is conceptually convenient.
# (Getting this wrong showed up as the buffer containing SECTION_CNT, i.e. the
# moderow tables, so the file read "succeeded" into memory that was then
# overwritten and HINT_LEN stayed 0.)
sub("hint", "cave_end:\n",
    "cave+6000:\nHINT_BUF:\ncave+7800:\nHINT_ARR:\ncave_end:\n",
    "reserve the hint file buffer last")


def main():
    want = {"bossfix", "moderow", "ui", "overlay", "seed", "hint"}  # all on
    if "--no-bossfix" in sys.argv:
        want.discard("bossfix")
    if "--no-moderow" in sys.argv:
        want.discard("moderow")
    if "--no-ui" in sys.argv:
        want.discard("ui")
    if "--no-overlay" in sys.argv:
        want.discard("overlay")
    if "--no-seed" in sys.argv:
        want.discard("seed")
    if "moderow" not in want:
        want.discard("ui")                 # ui builds on the Mode row

    text = open(SRC, encoding="utf-8").read()
    applied = 0
    for group, old, new, why in EDITS:
        if group not in want:
            continue
        n = text.count(old)
        if n != 1:
            raise SystemExit("anchor %r found %d times (expected 1) -- source drifted"
                             % (why, n))
        text = text.replace(old, new, 1)
        applied += 1
    open(DST, "w", encoding="utf-8", newline="\n").write(text)
    print("[+] wrote %s  (%d edits: %s)" % (DST, applied, ", ".join(sorted(want)) or "none"))


if __name__ == "__main__":
    main()
