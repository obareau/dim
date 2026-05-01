# D.I.M — Instruction Set Reference

> L'instruction set de D.I.M est inspiré de BASIC et des structures de contrôle
> fondamentales : IF/THEN/ELSE, GOTO, GOSUB, LOOP/UNTIL, SKIP/UNTIL, REVERSE/UNTIL.

---

## Instructions de Cue

| Instruction | Paramètres | Comportement |
|---|---|---|
| `PLAY` | — | Joue le cue, avance au suivant. **Défaut.** |
| `MUTE` | — | Consomme la durée, rien à afficher/faire. |
| `LOOP n` | `loop_count: int` | Répète n fois puis avance. |
| `LOOP UNTIL cond` | `condition` | Répète jusqu'à condition vraie. |
| `JUMP target` | `target: id` | Saut inconditionnel vers cue ou section. |
| `JUMP target IF cond` | `target`, `condition` | Saut conditionnel. |
| `GOSUB section` | `target: section_id` | Appelle une section, retourne ici après. |
| `SKIP` | — | Saute ce cue (durée = 0, no-op). |
| `SKIP UNTIL cond` | `condition` | Ignore ce cue jusqu'à condition vraie. |
| `IF cond THEN inst` | `condition`, `then_inst` | Branchement simple. |
| `IF cond THEN inst ELSE inst` | `condition`, `then_inst`, `else_inst` | Branchement complet. |

## Instructions de Section (en plus des cues)

| Instruction | Paramètres | Comportement |
|---|---|---|
| `REVERSE` | — | Lit les cues dans l'ordre inverse. |
| `REVERSE UNTIL cond` | `condition` | Inverse jusqu'à condition vraie. |

---

## Conditions

| Condition | Notation JSON | Sens |
|---|---|---|
| Toujours | `"ALWAYS"` | Inconditionnel (= PLAY direct) |
| Jamais | `"NEVER"` | = MUTE |
| 1 sur N | `"1:2"` `"1:4"` | Joue au 1er passage, saute les N-1 suivants |
| M sur N | `"3:4"` `"2:3"` | Joue M fois sur N passages |
| Probabiliste | `"50%"` `"25%"` | Dé lancé à chaque passage |
| Après N | `"AFTER:4"` | Joue seulement après N passages de la section |
| Action manuelle | `"MANUAL"` | Attend un tap/déclenchement performer |

---

## Notation compacte (affichage UI)

| Instruction | Badge affiché |
|---|---|
| `PLAY` | (aucun badge — état par défaut) |
| `MUTE` | `░ MUTE` |
| `LOOP 4` | `↺ 4` |
| `LOOP UNTIL MANUAL` | `↺ ⊙` |
| `JUMP refrain` | `↗ refrain` |
| `JUMP refrain IF 1:2` | `↗ refrain  1:2` |
| `GOSUB fill` | `⤵ fill` |
| `SKIP` | `⇥` |
| `SKIP UNTIL 2:4` | `⇥ 2:4` |
| `REVERSE` | `⇐ REV` |
| `IF 1:2 THEN JUMP ELSE PLAY` | `? 1:2 ↗/▶` |
| `IF 50% THEN LOOP ELSE MUTE` | `? 50% ↺/░` |

---

## Pile GOSUB

GOSUB empile le point de retour. Profondeur maximum configurable (défaut : 4).

```
ARRANGEMENT :
  sec-A → cue [GOSUB sec-fill] → sec-B
                   ↓
              sec-fill : cue1, cue2, cue3
                   ↑ retour automatique vers sec-A, cue suivant
```

Si la profondeur est dépassée : `PLAY` forcé + alerte visuelle non-bloquante.

---

## Cross-lane Jump

Un cue dans Lane A peut déclencher un saut dans Lane B :

```json
{
  "op": "JUMP",
  "target": "sec-refrain",
  "jump_lane": "lane-basse"
}
```

Convention : la **Conductor Lane** (`is_conductor: true`) est dédiée à l'orchestration.
Les musiciens voient leur propre lane. Le leader voit la Conductor.

---

## Exemples

### Cue qui saute au refrain une fois sur deux
```json
{ "op": "JUMP", "target": "sec-refrain", "condition": "1:2" }
```

### Section qui se joue à l'envers les passes impaires
```json
{ "op": "REVERSE", "condition": "1:2" }
```

### Cue probabiliste (50% de chance d'être muté)
```json
{ "op": "IF", "condition": "50%", "then_inst": {"op":"PLAY"}, "else_inst": {"op":"MUTE"} }
```

### Boucle jusqu'à action manuelle du performer
```json
{ "op": "LOOP", "condition": "UNTIL", "condition_value": "MANUAL" }
```

### Fill appelé en sous-routine 1 fois sur 2
```json
{ "op": "GOSUB", "target": "sec-fill-8bars", "condition": "1:2" }
```
