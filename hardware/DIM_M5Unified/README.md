# D.I.M — Firmware M5Stack (unifié)

Contrôleur hardware pour le séquenceur D.I.M.  
Fonctionne sur **M5Stack Core**, **Core2** et **StickC Plus** (auto-détecté).  
Polling HTTP toutes les 200 ms, affichage TFT adaptatif.

---

## Matériel supporté

| Device | Écran | Boutons |
|--------|-------|---------|
| M5Stack Core | 320×240 | A · B · C (sous l'écran) |
| M5Stack Core2 | 320×240 | A · B · C (touch, sous l'écran) |
| M5StickC Plus | 135×240 | A (face) · B (côté) |

---

## Boutons — Core / Core2

```
┌─────────────────────────┐
│         écran           │
└─────────────────────────┘
  [ A ]     [ B ]     [ C ]
 gauche    milieu    droite
```

| Bouton | Appui court | Maintenu 2 s |
|--------|-------------|--------------|
| **A** | Advance (1ère lane en MANUAL WAIT) | Play / Pause |
| **B** | Advance ALL (toutes les lanes en attente) | Rewind |
| **C** | Veto (annule le prochain JUMP) | — |

**Écran de config** : maintenir **A + B** à la mise sous tension.

---

## Boutons — StickC Plus

```
  [ A ]  ← face avant (grand bouton)
  [ B ]  ← bouton latéral
```

| Bouton | Appui court | Maintenu 2 s |
|--------|-------------|--------------|
| **A** | Advance | Play / Pause |
| **B** | Cycle : ALL → Veto → Rewind (tourne à chaque appui) | — |

**Écran de config** : maintenir **A** à la mise sous tension.

---

## Écran de configuration

S'ouvre automatiquement si le WiFi échoue ou si le serveur est introuvable.  
Peut être forcé en maintenant **A + B** au boot (Core/Core2) ou **A** (StickC).

### Menu principal

Navigue avec **A** (haut) / **C** (bas) — sélectionne avec **B** :

| Entrée | Description |
|--------|-------------|
| **SSID** | Nom du réseau WiFi |
| **PASS** | Mot de passe WiFi |
| **IP1** | IP principale du serveur D.I.M |
| **IP2** | IP alternative (gateway, secondaire) |
| **SAVE & REBOOT** | Sauvegarde en NVS et redémarre |

### Édition SSID / PASS (caractère par caractère)

| Bouton | Action |
|--------|--------|
| **A** | Caractère précédent |
| **C** | Caractère suivant |
| **B** | Déplace le curseur (ajoute un caractère si en fin de chaîne) |
| **B maintenu 2 s** (en fin de chaîne) | Valide et retourne au menu |

### Édition IP (octet par octet, 0–255)

| Bouton | Action |
|--------|--------|
| **A** | Valeur − 1 |
| **C** | Valeur + 1 |
| **B** | Octet suivant |

---

## WiFi & Discovery

Le firmware **ne nécessite pas de port fixe**. Au démarrage :

1. **Fast-path** : teste le dernier port connu (sauvegardé en NVS)
2. Si échec → **scan complet** des ports 5000 à 5010 sur IP1 puis IP2
3. Le port trouvé est sauvegardé en NVS pour le prochain boot
4. En cours de session, si 15 polls consécutifs échouent → re-scan automatique

---

## Installation Arduino IDE

1. `Fichier > Préférences > URLs supplémentaires` → ajouter :  
   `https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/arduino/package_m5stack_index.json`
2. `Outils > Gestionnaire de cartes` → installer **M5Stack by M5Stack**
3. `Outils > Gestionnaire de bibliothèques` → installer :
   - **M5Unified** (≥ 0.2.14)
   - **ArduinoJson** par Benoit Blanchon (≥ 7.0)
4. Sélectionner la bonne carte :
   - Core → `M5Stack-Core-ESP32`
   - Core2 → `M5Stack-Core2`
   - StickC Plus → `M5Stick-C-Plus`
5. Ouvrir `DIM_M5Unified/DIM_M5Unified.ino` → **Upload**

### Defaults à changer dans le .ino

```cpp
#define DEFAULT_SSID  "Augustine-free"   // ton SSID
#define DEFAULT_PASS  "14031972"         // ton mot de passe
#define DEFAULT_IP1   "192.168.1.28"     // IP de ta machine (serveur D.I.M)
#define DEFAULT_IP2   "192.168.1.1"      // IP alternative ou gateway
```

Ces valeurs sont les defaults au premier boot. Elles peuvent ensuite être changées via l'écran de config embarqué (sauvegardé en NVS).

---

## Flash via PlatformIO (CLI)

```bash
cd hardware/DIM_M5Unified

./flash.sh build core        # compile Core seulement
./flash.sh build core2       # compile Core2
./flash.sh build stickc      # compile StickC Plus
./flash.sh flash core        # compile + flash Core (USB auto-détecté)
./flash.sh flash core2 /dev/cu.usbserial-XXXX  # port explicite
./flash.sh bin               # compile tout + exporte .bin dans dist/
./flash.sh clean             # nettoie .pio/
```

## Flash via M5Burner (sans compiler)

Les `.bin` pré-compilés sont dans `dist/` :

```
dist/DIM_M5Unified_core_YYYYMMDD.bin       → M5Stack Core
dist/DIM_M5Unified_core2_YYYYMMDD.bin      → M5Stack Core2
dist/DIM_M5Unified_stickc_YYYYMMDD.bin     → M5StickC Plus
```

Dans M5Burner : **Custom flash** → sélectionner le `.bin` → adresse **0x10000**.

---

## Affichage (Core / Core2 — 320×240)

```
┌──────────────────────────────────────────────────────────────┐
│ D.I.M  PLAY   120 BPM  4/4  B03  0:42                       │  ← header
├──────────────────────────────────────────────────────────────┤
│█ 1  CONDUCTOR    GROOVE A               [MAN]                │
│  ████████████░░░░░░░░░░░░░░░░░░░░░░░   2.5                  │
├──────────────────────────────────────────────────────────────┤
│░ 2  DRUMS        BREAK 1               [LOOP]                │
│  ████████████████████████░░░░░░░░░░░   0.8                  │
├──────────────────────────────────────────────────────────────┤
│  [A]ADV  [B]ALL  [C]VTO | holdA=PLAY  holdB=REW             │  ← footer
└──────────────────────────────────────────────────────────────┘
```

| Couleur stripe gauche | Signification |
|-----------------------|---------------|
| 🟢 Vert | Lane en lecture |
| 🟠 Orange | Lane en MANUAL WAIT (appuie A ou B) |
| ⬜ Gris | Lane terminée / stoppée |

---

## Dépannage

| Symptôme | Cause probable | Solution |
|----------|---------------|----------|
| "WiFi FAIL" | SSID ou pass incorrect | Écran config (hold A+B) → SSID / PASS |
| "Introuvable" | Serveur D.I.M arrêté ou mauvaise IP | Vérifier que D.I.M tourne, corriger IP1 |
| "Injoignable" en cours de session | WiFi instable ou serveur coupé | Re-scan automatique au bout de 15 échecs |
| Écran blanc | Mauvaise board sélectionnée | Recompiler avec la bonne carte dans l'IDE |
| Toujours port 5002 | Port 5002 sauvegardé en NVS | Hold A+B → SAVE & REBOOT pour forcer re-scan |

---

## Commandes utiles (macOS)

### Lancer le serveur D.I.M sur le port 5001
```bash
python run_web.py --port 5001
```

### Vérifier ce qui tourne sur le port 5001
```bash
lsof -i :5001
```

### Tuer le process sur le port 5001
```bash
lsof -ti :5001 | xargs kill -9
```

### Tuer n'importe quel port (remplacer 5001)
```bash
lsof -ti :PORT | xargs kill -9
```
