# D.I.M — Instruction Set Reference

> D.I.M's instruction set is directly inspired by BASIC and fundamental control flow
> structures: IF/THEN/ELSE, GOTO, GOSUB, LOOP/UNTIL, SKIP/UNTIL, REVERSE/UNTIL.
>
> Every cue and every section carries exactly **one instruction**.

---

## Cue Instructions

| Instruction | Parameters | Behavior |
|---|---|---|
| `PLAY` | — | Play the cue, advance to next. **Default.** |
| `MUTE` | — | Consume the duration, nothing to perform. |
| `LOOP n` | `loop_count: int` | Repeat n times, then advance. |
| `LOOP UNTIL cond` | `condition` | Repeat until condition becomes true. |
| `JUMP target` | `target: id` | Unconditional jump to a cue or section. |
| `JUMP target IF cond` | `target`, `condition` | Conditional jump. |
| `GOSUB section` | `target: section_id` | Call a section, return here after. |
| `SKIP` | — | Skip this cue (duration = 0, no-op). |
| `SKIP UNTIL cond` | `condition` | Skip this cue until condition is true. |
| `IF cond THEN inst` | `condition`, `then_inst` | Simple branch. |
| `IF cond THEN inst ELSE inst` | `condition`, `then_inst`, `else_inst` | Full branch. |

## Section Instructions (in addition to all cue instructions)

| Instruction | Parameters | Behavior |
|---|---|---|
| `REVERSE` | — | Play cues in reverse order. |
| `REVERSE UNTIL cond` | `condition` | Reverse until condition, then resume normal order. |

---

## Conditions

| Condition | JSON value | Meaning |
|---|---|---|
| Always | `"ALWAYS"` | Unconditional (equivalent to direct PLAY or JUMP) |
| Never | `"NEVER"` | Never triggers (equivalent to MUTE) |
| 1 out of N | `"1:2"` `"1:4"` | Play on pass 1, skip next N-1 passes |
| M out of N | `"3:4"` `"2:3"` | Play M times out of every N passes |
| Probabilistic | `"50%"` `"25%"` | Die rolled at each pass through the section |
| After N passes | `"AFTER:4"` | Only triggers after N passes of the parent section |
| Manual trigger | `"MANUAL"` | Wait for a performer tap or external trigger |

---

## Compact Notation (UI display)

| Instruction | Badge shown |
|---|---|
| `PLAY` | *(no badge — default state)* |
| `MUTE` | `░ MUTE` |
| `LOOP 4` | `↺ 4` |
| `LOOP UNTIL MANUAL` | `↺ ⊙` |
| `JUMP chorus` | `↗ chorus` |
| `JUMP chorus IF 1:2` | `↗ chorus  1:2` |
| `GOSUB fill` | `⤵ fill` |
| `SKIP` | `⇥` |
| `SKIP UNTIL 2:4` | `⇥ 2:4` |
| `REVERSE` | `⇐ REV` |
| `IF 1:2 THEN JUMP ELSE PLAY` | `? 1:2 ↗/▶` |
| `IF 50% THEN LOOP ELSE MUTE` | `? 50% ↺/░` |

---

## GOSUB — Call Stack

GOSUB pushes a return address onto the call stack.
Maximum depth is configurable per project (default: 4).

```
ARRANGEMENT:
  sec-A → cue [GOSUB sec-fill] → sec-B
                   ↓
              sec-fill: cue1, cue2, cue3
                   ↑ automatically returns to sec-A, next cue
```

If the stack depth is exceeded: forced `PLAY` + non-blocking visual alert (2 seconds).
The performance is never interrupted.

Nested GOSUB (section A calls B which calls C) is valid up to the configured depth.

---

## Cross-lane Jump

A cue in Lane A can trigger a jump in Lane B:

```json
{
  "op": "JUMP",
  "target": "sec-chorus",
  "jump_lane": "lane-bass"
}
```

**Conductor Lane convention**: a lane with `is_conductor: true` is dedicated to
orchestrating other lanes. The band leader watches the Conductor Lane;
each performer watches their own lane.

Cross-lane GOSUB is also valid: call a section in another lane, return after.

---

## JSON Representation

Each instruction is a JSON object on the cue or section:

```json
{ "op": "PLAY" }

{ "op": "MUTE" }

{ "op": "LOOP", "loop_count": 4 }

{ "op": "LOOP", "loop_until": true, "condition": "MANUAL" }

{ "op": "JUMP", "target": "sec-chorus" }

{ "op": "JUMP", "target": "sec-chorus", "condition": "1:2" }

{ "op": "JUMP", "target": "sec-refrain", "jump_lane": "lane-bass" }

{ "op": "GOSUB", "target": "sec-fill-8bars" }

{ "op": "GOSUB", "target": "sec-fill-8bars", "condition": "1:2" }

{ "op": "SKIP" }

{ "op": "SKIP", "condition": "2:4" }

{ "op": "REVERSE" }

{ "op": "REVERSE", "condition": "1:2" }

{
  "op": "IF",
  "condition": "50%",
  "then_inst": { "op": "PLAY" },
  "else_inst": { "op": "MUTE" }
}

{
  "op": "IF",
  "condition": "1:2",
  "then_inst": { "op": "JUMP", "target": "sec-chorus" },
  "else_inst": { "op": "LOOP", "loop_count": 2 }
}
```

---

## Examples

### Jump to chorus every other pass
```json
{ "op": "JUMP", "target": "sec-chorus", "condition": "1:2" }
```

### Section plays in reverse on odd passes
```json
{ "op": "REVERSE", "condition": "1:2" }
```

### Probabilistic cue (50% chance of being muted)
```json
{ "op": "IF", "condition": "50%",
  "then_inst": { "op": "PLAY" },
  "else_inst": { "op": "MUTE" } }
```

### Loop until manual performer trigger
```json
{ "op": "LOOP", "loop_until": true, "condition": "MANUAL" }
```

### Fill called as subroutine every other time
```json
{ "op": "GOSUB", "target": "sec-fill-8bars", "condition": "1:2" }
```

### Cross-lane: trigger bass lane to jump to chorus
```json
{ "op": "JUMP", "target": "sec-chorus", "jump_lane": "lane-bass" }
```

### Skip this cue for the first 3 passes out of 4
```json
{ "op": "SKIP", "condition": "1:4" }
```
*(plays only on pass 1, skipped on passes 2, 3, 4, then resets)*
