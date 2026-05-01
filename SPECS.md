# D.I.M — Dawless Is More
## Cahier des charges — v0.1

> *"D.I.M sequences the human, not the machine."*
> Le tempo est roi. La machine guide. Le musicien joue.

---

## 1. Vision & Philosophie

### 1.1 Concept

D.I.M est un **séquenceur de performance pour musicien humain**.
Il ne contrôle aucun instrument, aucune machine, aucun plugin.
Il guide le musicien : quoi jouer, quand, dans quel ordre, avec quelles variations.

Analogie : le road book du Paris-Dakar. Le pilote conduit. Le copilote lit et annonce.
D.I.M est le copilote. Le musicien est le pilote.

### 1.2 Principes fondamentaux

- **Le tempo est roi** — tout est exprimé en mesures/beats, les secondes sont dérivées
- **Non-linéaire par conception** — le set n'est pas un fichier audio figé, il vit
- **Zéro latence perceptible** — l'affichage ne doit jamais faire douter le musicien
- **No brainer** — lisible en < 1 seconde, utilisable avec les mains mouillées, sous les spots
- **Multi-musicien** — une instance par performer, un master pour orchestrer
- **Interopérable** — parle les protocoles standards (Ableton Link, MIDI Clock, OSC)

### 1.3 Ce que D.I.M N'est PAS

- Pas un séquenceur MIDI/CV (il ne séquence pas les machines)
- Pas un DAW (pas d'enregistrement, pas de pistes audio)
- Pas un prompteur simple (la structure est non-linéaire et conditionnelle)
- Pas un gestionnaire de samples

---

## 2. Concepts fondamentaux

### 2.1 Hiérarchie des objets

```
Project
  └── Lane(s)          — un instrument, un rôle, un performer
        └── Section(s) — bloc structurel (intro, couplet, refrain...)
              └── Cue(s) — action atomique à exécuter
```

### 2.2 Le Cue — atome de base

Le cue est l'unité indivisible. Il représente **une action à faire**.
Exemples : "Joue le patch VOID_01", "Coupe le filtre", "Improvise sur la gamme de Ré mineur".

Attributs d'un cue :
```
label           — nom court, affiché en grand
content         — instructions détaillées (patch, réglages, note)
duration_bars   — durée en mesures (float : 0.5, 1, 2, 4, 8...)
repeat          — nombre de répétitions (1 = pas de répétition)
instruction     — PLAY | MUTE | LOOP | JUMP | GOSUB | SKIP | REVERSE | IF
condition       — 1:2 | 3:4 | 50% | MANUAL | ALWAYS | NEVER
jump_target     — cue_id ou section_id (si instruction JUMP/GOSUB)
jump_lane       — lane_id (pour cross-lane jump)
enabled         — booléen — coché/décoché dans la playlist
order_index     — position réorderable dans la section
```

### 2.3 La Section — bloc structurel

Regroupement de cues. Représente une partie du morceau.

Types prédéfinis : `intro` `couplet` `refrain` `bis` `alternative`
                   `fill` `break` `outro` `fin` + `custom` (texte libre)

Attributs d'une section :
```
name, type, color
instruction     — même instruction set que les cues
playlist        — mode de sélection des cues actifs (all / nth / ratio / custom)
reverse_flag    — lit les cues dans l'ordre inverse
```

### 2.4 La Lane — un performer / un instrument

Colonne verticale représentant un rôle dans le set.

```
name            — "Synthé principal" | "Basse" | "Drums" | "FX" | "Conductor"
color           — couleur distincte dans l'UI
speed_ratio     — "1:1" (défaut) | "2:1" | "4:1" | "1:2" | "1:4"
                  — toujours multiple/sous-multiple du tempo maître
is_conductor    — si True, cette lane peut envoyer des commandes aux autres lanes
sections        — liste ordonnée des sections dans cette lane
```

**Speed ratio** : une lane à 2:1 joue deux fois plus vite. Ses mesures sont deux fois plus
courtes. La synchronisation se fait sur le downbeat global.

Nombre de lanes : **1 à 8** (au-delà, l'ergonomie tactile se dégrade).
Recommandation affichage simultané : **1 à 6**.

### 2.5 L'Arrangement global

Chaque lane définit sa propre séquence de sections. Un "arrangement global"
optionnel synchronise les points de passage entre lanes sur les downbeats communs.

---

## 3. L'Instruction Set

Inspiration directe de BASIC et des structures de contrôle de flux.
Chaque cue ET chaque section porte **une instruction**.

### 3.1 Instructions de base

| Instruction | Niveau | Comportement |
|---|---|---|
| `PLAY` | Cue + Section | Joue normalement, avance au suivant. Défaut. |
| `MUTE` | Cue + Section | Consomme le temps, rien à faire. Silence visuel. |
| `LOOP n` | Cue + Section | Répète n fois puis avance |
| `LOOP UNTIL cond` | Cue + Section | Répète jusqu'à condition vraie |
| `JUMP target` | Cue + Section | Saut inconditionnel vers cue/section |
| `JUMP target IF cond` | Cue + Section | Saut conditionnel |
| `GOSUB section` | Cue + Section | Appelle une section, **retourne ici** après |
| `SKIP` | Cue | Saute ce cue (durée = 0) |
| `SKIP UNTIL cond` | Cue | Ignore jusqu'à condition vraie |
| `REVERSE` | Section | Lit les cues dans l'ordre inverse |
| `REVERSE UNTIL cond` | Section | Inverse jusqu'à condition, puis reprend normal |
| `IF cond THEN inst` | Cue + Section | Branchement simple |
| `IF cond THEN inst ELSE inst` | Cue + Section | Branchement complet |

### 3.2 Conditions

| Condition | Notation | Sens |
|---|---|---|
| Toujours | `ALWAYS` | Inconditionnel |
| Jamais | `NEVER` | = MUTE / SKIP |
| Nth passage | `1:2` `1:4` `3:4` | 1 fois sur 2 / 3 fois sur 4 |
| Probabiliste | `50%` `25%` `75%` | Dé lancé à chaque passage |
| Action manuelle | `MANUAL` | Attend un tap/déclenchement performer |
| Compteur | `AFTER 4` | Après 4 passages de cette section |

### 3.3 Cross-lane Jump

Un cue dans Lane A peut déclencher un saut dans Lane B :
```json
{ "instruction": "JUMP", "target": "sec-refrain", "jump_lane": "lane-basse" }
```

La **Conductor Lane** est la convention recommandée :
une lane dédiée à l'orchestration des autres, visible par le leader.

### 3.4 GOSUB — pile d'appel

GOSUB crée une structure de sous-routine : une section peut être "appelée" depuis
plusieurs points et retourne au point d'appel après exécution.

Profondeur maximum configurable (défaut : 4 niveaux).
Dépassement → `PLAY` forcé + alerte visuelle non-bloquante.

### 3.5 Playlist de section

La playlist définit quels cues jouer et dans quel ordre au sein d'une section :

| Mode | Comportement |
|---|---|
| `all` | Tous les cues enabled, dans l'ordre |
| `nth:2` | 1 cue sur 2 |
| `ratio:3:4` | 3 cues sur 4 |
| `custom` | Ordre et sélection libres définis manuellement |

Chaque cue peut être coché/décoché (enabled) et réordonné dans la playlist.

---

## 4. Timing & Synchronisation

### 4.1 Unités

L'unité primaire est la **mesure (bar)**. Les secondes sont dérivées.

```
beats_per_bar    = numérateur de la signature (4/4 → 4, 3/4 → 3, 7/8 → 7)
sec_per_beat     = 60 / tempo_bpm
sec_per_bar      = sec_per_beat × beats_per_bar
cue_duration_sec = cue.duration_bars × sec_per_bar
```

Signatures supportées : `4/4` `3/4` `6/8` `7/8` `5/4` `12/8` + signature libre.

### 4.2 Ableton Link

**Intégration prioritaire.** Ableton Link est un protocole peer-to-peer de
synchronisation du tempo et de la position de beat sur réseau local (UDP multicast).

Comportement dans D.I.M :
- D.I.M peut **rejoindre** une session Link existante (Ableton, apps iOS, etc.)
- D.I.M peut être **la source** du tempo de la session Link
- Synchronisation automatique dès qu'une session Link est détectée sur le réseau
- Pas de master/slave : protocole symétrique — tous les pairs négocient

Bibliothèque Python : `python-link` (binding officiel Ableton Link SDK).

### 4.3 MIDI Clock

- **Réception** : D.I.M suit une horloge MIDI Clock externe (24 PPQN)
- **Émission** : D.I.M envoie une horloge MIDI Clock (pour synchroniser du hardware)
- Support USB MIDI + DIN MIDI (via adaptateur)
- Messages : `CLOCK` (24/QN) `START` `STOP` `CONTINUE`

### 4.4 OSC (Open Sound Control)

- Protocole natif D.I.M pour la communication inter-instances
- Compatible avec Ableton (via plugins OSC), Max/MSP, PureData, SuperCollider, TouchOSC
- UDP — latence < 1ms sur LAN

### 4.5 Synchronisation multi-instance

```
Priorité de sync (décroissante) :
  1. Ableton Link (si session détectée sur le réseau)
  2. MIDI Clock externe reçu
  3. Horloge D.I.M Master (OSC broadcast)
  4. Horloge interne (standalone)
```

Résolution des conflits : la source de plus haute priorité détectée l'emporte.
Changement de source → crossfade de tempo (pas de saut brutal).

---

## 5. Architecture Réseau

### 5.1 Topologie

```
MASTER D.I.M (laptop / RPi central)
│
├── Ableton Link session (partagée avec DAW, apps iOS, etc.)
├── OSC broadcast → toutes instances D.I.M
├── WebSocket server → état temps réel
├── REST API → management projets + instances
│
├── D.I.M Instance 2 (RPi — Synthé)
├── D.I.M Instance 3 (RPi — Drums)
├── D.I.M Instance 4 (ESP32 — FX monitor)
└── TouchOSC / Lemur (surface de contrôle)
```

### 5.2 Protocoles par couche

| Couche | Protocole | Port | Latence cible |
|---|---|---|---|
| Sync beat/tempo | Ableton Link (UDP multicast) | 20808 | < 1 ms |
| Sync transport | OSC / UDP | 7400 | < 1 ms |
| État temps réel | WebSocket | 7401 | < 10 ms |
| Management | REST HTTP | 5000 | < 100 ms |
| Accès humain | SSH + TUI | 22 | — |
| Discovery | mDNS / Bonjour | — | auto |

### 5.3 OSC Address Space

```
# Transport
/dim/transport/play
/dim/transport/stop
/dim/transport/pause
/dim/transport/rewind
/dim/transport/tempo        f:120.0
/dim/transport/jump         s:"section-id"

# Sync
/dim/sync/beat              i:<beat>  i:<bar>  t:<timestamp>

# Lane control
/dim/lane/<id>/mute
/dim/lane/<id>/unmute
/dim/lane/<id>/jump         s:"section-id"
/dim/lane/<id>/speed        s:"2:1"

# Instance → Master (reporting)
/dim/report/<name>/beat     i:<beat>  i:<bar>
/dim/report/<name>/state    s:<json>

# Orchestrateur → instance
/dim/instance/<name>/play
/dim/instance/<name>/project  s:<json>
/dim/instance/all/sync
```

### 5.4 Auto-discovery

Chaque instance annonce sa présence via **mDNS (Zeroconf/Bonjour)** :
```
dim-synthé._dim._tcp.local   port 5000 (HTTP) + 7400 (OSC)
```
Aucune configuration IP manuelle. Branchement → apparition automatique.
ESP32 : mDNS via bibliothèque ESP-IDF native.

---

## 6. Interfaces

### 6.1 Philosophie UI

**Référence design : Teenage Engineering × Elektron**

- Teenage Engineering : chaque pixel est intentionnel. Zéro décoration. Fonctionnel = beau.
- Elektron : densité d'information, notation compacte, toutes les infos critiques visibles.

**Règles fondamentales :**
1. Lisible en < 1 seconde dans n'importe quelle condition de lumière
2. Cibles tactiles ≥ 44px (norme Apple HIG) — utilisable avec les doigts, pas un stylet
3. Contraste élevé — mode sombre par défaut (scène = lumière basse)
4. Pas d'animation superflue — les animations ont une fonction sémantique
5. Un seul écran pour la performance — zéro navigation pendant le jeu
6. Informations par ordre de priorité : **cue courant → suivant → position → temps**

### 6.2 Interface Web (adapter principal)

Deux modes distincts :

**Mode Éditeur** (desktop + tablet landscape) :
- Vue grille : lanes en lignes, sections en colonnes colorées
- Panneau latéral contextuel : clic sur section → détail cues + instruction + playlist
- Drag & drop pour réordonner sections et cues
- Panneau tempo en haut : BPM, signature, Link status, sync source

**Mode Performance** (tous appareils, plein écran) :
- Lane(s) en focus : section précédente (dim) | section courante | section suivante (dim)
- Cue courant affiché en grand au centre
- Countdown beats/bars dans coin supérieur droit
- Topbar : BPM | signature | mesure courante | temps écoulé | indicateur Link
- Transport : ⏮ ⏹ ▶/⏸ — toujours accessibles
- Instruction badges : `LOOP 4` `↗ refrain` `↺ 1:2` `GOSUB fill`

### 6.3 Breakpoints responsive

| Contexte | Résolution | Mode | Lanes visibles |
|---|---|---|---|
| Desktop | > 1200px | Éditeur + Performance | 1 à 8 |
| Tablet landscape | 1024px | Performance + édition légère | 1 à 6 |
| Tablet portrait / RPi 7" | 768px | Performance | 1 à 4 |
| Phone / RPi 3.5" | 480px | Performance 1 lane focus | 1 |
| ESP32 TFT 320×240 | 320px | Cue courant + suivant | 1 |
| ESP32 OLED 128×64 | 128px | Cue courant uniquement | 1 |

### 6.4 TUI — Terminal User Interface

Implémentée avec **Textual** (Python).

Accessible via :
- Terminal local
- SSH (`.bashrc` → lance la TUI automatiquement)
- Tmux/screen pour sessions persistantes

Deux vues :
- **Performance** : même information que le web, rendu ASCII/Unicode
- **Orchestrateur** : grille de toutes les instances connues, état en temps réel

```
┌─ D.I.M ──────────────────── ▶ 118 BPM  4/4  ♩32  02:14 ─┐
│ CONDUCTOR │░░░░████████░░│ REFRAIN      COUPLET 2         │
├───────────┼──────────────┼──────────────────────────────── ┤
│ SYNTHÉ 1:1│ [LOOP 2]     │ ▶ pad-void   ↺ 1:2            │
├───────────┼──────────────┼──────────────────────────────── ┤
│ BASSE 2:1 │ MUTE ░░░░░░░ │ ▶ sub-bass   SKIP 2:4         │
└───────────┴──────────────┴──────────────────────────────── ┘
 [SPC] next  [←][→] nav  [M] mute  [L] loop  [S] stop  [?]
```

### 6.5 ESP32 — Client display

L'ESP32 est un **client lecture seule**. Il ne fait pas tourner de logique de séquencement.
Il reçoit l'état courant depuis le serveur D.I.M via WiFi (WebSocket ou polling HTTP).

**TFT 320×240 (ILI9341)** :
- Cue courant (grand) + cue suivant (petit)
- Barre de progression beats
- Instruction badge
- Bouton tactile : next / prev / stop

**OLED 128×64 (SSD1306)** :
- Cue courant uniquement
- Beat counter
- Montre de bord minimale

Connexion : WiFi → WebSocket → subscribe au state de sa lane assignée.

---

## 7. Architecture Technique

### 7.1 Structure projet

```
dim/
  core/                        # Python pur — zéro dépendance framework
    models.py                  # Dataclasses : Project, Lane, Section, Cue, Instruction
    timing.py                  # BPM/bars/sec, speed_ratio, downbeat, conversions
    instruction.py             # Évaluation instruction set (PLAY/LOOP/GOSUB/JUMP...)
    condition.py               # Évaluation conditions (1:2, 50%, MANUAL...)
    sequencer.py               # tick() pur, curseur multi-lane, pile GOSUB
    playlist.py                # Construction queue cues dans une section
    serializer.py              # JSON ↔ modèles (format canonique versionné)
    validator.py               # Validation projet (cycles, jumps invalides, stack depth)

  network/
    osc/
      server.py                # Réception UDP OSC, dispatch handlers
      client.py                # Émission OSC (unicast + broadcast)
      messages.py              # Address patterns, types, encodage/décodage
      handlers.py              # Handlers /dim/transport/*, /dim/lane/*, etc.
    websocket/
      server.py                # Flask-SocketIO
      events.py                # Events : state_update, beat, sync, instance_list
    rest/
      blueprint.py             # CRUD projets, instances, config
      schema.py                # Validation requêtes/réponses
    discovery/
      mdns.py                  # Zeroconf — announce + browse
      registry.py              # Instances connues, état, timestamp
    orchestrator/
      master.py                # Logique maître — gestion instances
      sync.py                  # Algorithme synchronisation beat multi-instance
      proxy.py                 # InstanceProxy — abstraction instance distante
    link/
      link_session.py          # Intégration Ableton Link (python-link)
      link_bridge.py           # Bridge Link ↔ OSC D.I.M
    midi/
      clock_receiver.py        # Réception MIDI Clock (24 PPQN)
      clock_sender.py          # Émission MIDI Clock
      midi_bridge.py           # Bridge MIDI Clock ↔ séquenceur D.I.M

  adapters/
    web/
      app.py                   # Flask application factory
      blueprints/              # Routes par domaine
      templates/               # Jinja2 — Éditeur + Performance
      static/                  # CSS vanilla + JS léger (pas de framework)
    tui/
      app.py                   # Textual Application
      screens/
        performance.py         # Vue scène
        orchestrator.py        # Vue master
      widgets/                 # Composants Textual
    esp32/
      main.py                  # Point d'entrée MicroPython
      wifi_sync.py             # Connexion WiFi + WebSocket client
      display_tft.py           # ILI9341 320×240
      display_oled.py          # SSD1306 128×64
      micro_models.py          # Sous-ensemble modèles (dataclasses → dicts)

  tests/
    test_timing.py
    test_instruction.py
    test_condition.py
    test_sequencer.py          # Scénarios complets (GOSUB, cross-lane, Link sync)
    test_playlist.py
    test_serializer.py

  docs/
    instruction_set.md         # Référence complète instructions + conditions
    format_v1.md               # Spec JSON canonique versionné
    design_language.md         # Règles UI (TE/Elektron)
    sync_protocols.md          # Ableton Link, MIDI Clock, OSC — guide d'intégration
    osc_address_space.md       # Référence complète OSC

  formats/
    example_project.json       # Projet exemple commenté
    schema_v1.json             # JSON Schema validation

  requirements.txt
  requirements-dev.txt
  .gitignore
  LICENSE
  README.md
  SPECS.md                     # Ce document
  CHANGELOG.md
```

### 7.2 Dépendances Python

```
# Core
python >= 3.11

# Web + réseau
flask >= 3.0
flask-socketio >= 5.0
python-osc >= 1.8            # OSC server + client
zeroconf >= 0.80             # mDNS discovery

# TUI
textual >= 0.50

# Sync protocols
python-link >= 0.0.1         # Ableton Link SDK binding
python-rtmidi >= 1.5         # MIDI Clock

# Dev + tests
pytest
pytest-asyncio
black
ruff
```

### 7.3 Format JSON canonique

```json
{
  "dim_version": "1.0",
  "project": {
    "id": "uuid",
    "name": "Set Robōtariis — Live 2026",
    "tempo_bpm": 118.0,
    "time_signature": "4/4",
    "gosub_stack_limit": 4,
    "lanes": [
      {
        "id": "lane-conductor",
        "name": "Conductor",
        "color": "#888888",
        "speed_ratio": "1:1",
        "is_conductor": true,
        "sections": []
      },
      {
        "id": "lane-synth",
        "name": "Synthé principal",
        "color": "#FF4D26",
        "speed_ratio": "1:1",
        "is_conductor": false,
        "sections": [
          {
            "id": "sec-intro",
            "name": "Drone d'ouverture",
            "type": "intro",
            "color": "#2A2A2A",
            "instruction": { "op": "LOOP", "loop_count": 2 },
            "playlist": { "mode": "all" },
            "cues": [
              {
                "id": "cue-001",
                "label": "Drone grave",
                "content": "Patch VOID_01 — filtre fermé cutoff 40% — réverb max",
                "duration_bars": 8.0,
                "repeat": 1,
                "instruction": { "op": "PLAY" },
                "enabled": true,
                "order_index": 0
              }
            ]
          }
        ]
      }
    ],
    "arrangement": ["sec-intro", "sec-couplet", "sec-refrain"]
  }
}
```

### 7.4 Principe de conception — tick() pur

La règle d'or : `tick()` est une **fonction pure**.

```python
def tick(cursor: PlaybackCursor, delta_beats: float, project: Project
        ) -> tuple[PlaybackCursor, list[Event]]:
    """
    Avance le curseur de delta_beats.
    Retourne le nouveau curseur et la liste des événements produits.
    Aucun effet de bord. Testable de manière déterministe.
    """
```

Tous les effets (affichage, envoi OSC, sons) sont gérés par les adapters
qui consomment la liste d'événements retournée.

---

## 8. Ergonomie & Design Language

### 8.1 Palette et typographie

- **Fond** : near-black `#0D0D0D` (performance) / `#111111` (éditeur)
- **Texte principal** : `#E8E4DC` (warm white)
- **Accent** : couleur par lane, saturée, ≥ 4.5:1 contraste sur fond
- **Muted** : `#555555`
- **Danger/Urgent** : `#FF4D26`
- **Typo** : IBM Plex Mono (labels, codes) + IBM Plex Sans (corps)
- **Taille cue courant** : ≥ 24px sur mobile, ≥ 32px sur desktop

### 8.2 Notation compacte (style Elektron)

| Instruction | Rendu badge |
|---|---|
| `LOOP 4` | `↺ 4` |
| `JUMP refrain` | `↗ refrain` |
| `GOSUB fill` | `⤵ fill` |
| `MUTE` | `░ MUTE` |
| `SKIP UNTIL 1:4` | `⇥ 1:4` |
| `IF 1:2 THEN JUMP` | `? 1:2 ↗` |
| `REVERSE` | `⇐ REV` |
| `50%` | `⚄ 50%` |

### 8.3 États visuels

- **Cue courant** : fond fort, texte max, badge instruction bien visible
- **Cue suivant** : opacité 55%, léger décalage
- **Cue précédent** : opacité 30%
- **Section muted** : fond hachuré `░`, texte grisé
- **Beat counter** : barre de progression par beats (pas par secondes)
- **Sync Link** : indicateur discret en topbar — vert si connecté, absent si solo
- **Alerte GOSUB overflow** : flash rouge non-bloquant, 2 secondes

### 8.4 Interactions tactiles

- Swipe gauche/droite : cue suivant/précédent
- Tap zone bas : stop
- Long press sur section : accès rapide instruction
- Pinch : zoom police (40% à 250%)
- Tous les boutons : ≥ 44×44px
- Retour haptique sur les transitions critiques (si disponible)

---

## 9. Plateformes cibles

| Plateforme | Interface | Notes |
|---|---|---|
| macOS / Linux desktop | Web (Flask) + TUI | Éditeur complet + performance |
| Windows | Web (Flask) | TUI possible via WSL |
| Raspberry Pi 4 + écran 7" | Web kiosk (Chromium) | Même code web, CSS responsive |
| Raspberry Pi Zero 2 + 3.5" | Web kiosk | 1-2 lanes, gros texte |
| Raspberry Pi headless | TUI via SSH | Performance ou orchestrateur |
| ESP32 + TFT ILI9341 320×240 | MicroPython client | Affichage cue + suivant |
| ESP32 + OLED SSD1306 128×64 | MicroPython client | Cue courant + beat |
| iPad / tablet | Web responsive | Performance tactile |
| iPhone | Web responsive | 1 lane focus |

---

## 10. Décisions architecturales actées

| Sujet | Décision |
|---|---|
| Nom | **D.I.M — Dawless Is More** |
| Paradigme | Séquencer l'humain, pas la machine |
| Unité temporelle | Mesures (bars) — secondes dérivées |
| Sync prioritaire | Ableton Link > MIDI Clock > OSC Master > horloge interne |
| Sync inter-instances | OSC UDP (transport) + WebSocket (état) |
| Discovery | mDNS / Bonjour — zéro config |
| Control flow | Instruction set BASIC-inspiré : 8 instructions, 6 types de conditions |
| Cross-lane | JUMP / GOSUB inter-lane via Conductor Lane |
| ESP32 | Client lecture seule — reçoit état depuis serveur Flask |
| TUI | Textual (Python) — local + SSH |
| Web | Flask + vanilla CSS — aucun framework JS |
| Tests | pytest — `tick()` pur testable de manière déterministe |
| Format data | JSON canonique versionné (`dim_version`) |
| Design | Teenage Engineering × Elektron — dense, fonctionnel, haute lisibilité |

---

## 11. Hors périmètre (explicitement exclus)

- Séquençage MIDI/CV des instruments
- Enregistrement audio
- Mixage
- Effets audio
- Gestion de samples
- Notation musicale (partitions)
- Synchronisation vidéo
- Gestion de comptes utilisateurs (v1 = single-user / réseau local de confiance)

---

## 12. Roadmap

```
v0.1 — Core pur (Sprint 1)
  core/ complet : models, timing, instruction, condition, sequencer, playlist
  Testable en CLI : python -m dim.cli play example.json
  Couverture tests > 80%

v0.2 — Interface Web (Sprint 2)
  Flask + éditeur projet basique
  Vue performance responsive (web)
  Export/import JSON

v0.3 — Sync (Sprint 3)
  Ableton Link (python-link)
  MIDI Clock reception
  OSC inter-instances basique

v0.4 — TUI + SSH (Sprint 4)
  Textual performance view
  TUI orchestrateur (multi-instances)

v0.5 — Réseau complet (Sprint 5)
  mDNS discovery
  WebSocket state broadcast
  Master orchestrateur
  ESP32 client (TFT)

v1.0 — Release publique
  Documentation complète
  Exemple projects
  Packaging (pip install dim)
  Docker image
```

---

*D.I.M — Dawless Is More*
*"The machine does not lie. It deforms."*

*Cahier des charges v0.1 — Mai 2026 — Olivier Bareau, Scaër, Bretagne*
