# D.I.M — M5Stack Core firmware

Contrôleur hardware pour le séquenceur D.I.M.  
Polling HTTP toutes les 200 ms, 3 boutons, affichage TFT 320×240.

## Matériel requis

- **M5Stack Core** (le boîtier noir avec 3 boutons A/B/C)
- Réseau WiFi partagé avec le serveur D.I.M

## Installation Arduino IDE

1. **Board Manager** → ajouter l'URL :  
   `https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/arduino/package_m5stack_index.json`
2. Installer **M5Stack** (boards)
3. Sélectionner **M5Stack-Core-ESP32**

### Bibliothèques (Library Manager)
- `M5Stack` (officielle M5Stack)
- `ArduinoJson` par Benoit Blanchon — version **6.x**

## Configuration

Éditer les constantes en tête du `.ino` :

```cpp
#define DEFAULT_WIFI_SSID   "YourSSID"
#define DEFAULT_WIFI_PASS   "YourPassword"
#define DEFAULT_IP1         "192.168.1.100"   // IP machine macOS
#define DEFAULT_IP2         "192.168.1.1"     // IP alternative / gateway
// Port : scan automatique 5000–5010, pas besoin de configurer
```

Le **port est détecté automatiquement** : au démarrage, le firmware balaie les ports 5000 à 5010 sur chaque IP jusqu'à trouver un serveur D.I.M qui répond.  
Le port trouvé est sauvegardé en NVS et réutilisé au prochain démarrage.  
Les autres valeurs (SSID, pass, IPs) sont configurables via l'écran de config embarqué.

## Boutons

| Bouton | Court | Long (2 s) |
|--------|-------|------------|
| **A** (gauche) | Advance première lane en attente | Play / Pause |
| **B** (centre) | Advance TOUTES les lanes en attente | Rewind → Stop |
| **C** (droite) | Véto JUMP (prochaine lane active) | — |
| **A + C** au démarrage | Écran de configuration | — |

## Écran de configuration

Si les 2 IPs ne répondent pas au démarrage, l'écran config s'ouvre automatiquement.  
On peut aussi le forcer en maintenant **A + C** à la mise sous tension.

- **BtnA** : valeur − 1
- **BtnC** : valeur + 1  
- **BtnB** : champ suivant
- **BtnB maintenu 2 s** sur le champ `[SAVE]` : sauvegarde en NVS et redémarre

Champs éditables : IP1 (4 octets), IP2 (4 octets).  
Le PORT n'est plus dans la config (découverte automatique 5000–5010).

## Affichage

```
┌──────────────────────────────────────────────────┐
│ D.I.M  PLAY  120 BPM  4/4  BAR 03 B2   1:24     │  ← header
├──────────────────────────────────────────────────┤
│█ 1  CONDUCTOR    GROOVE A          [LOOP ∞]      │
│  ████████████░░░░░░░░░░░░░░░░░░░  2.5           │
├──────────────────────────────────────────────────┤
│░ 2  DRUMS        BREAK 1           [LOOP 4×]     │
│  ████████████████████████░░░░░░░  0.8           │
├──────────────────────────────────────────────────┤
│  [A] ADV     [B] ALL     [C] VETO                │  ← footer
│  Hold: A=PLAY  B=REW  A+C=CFG                    │
└──────────────────────────────────────────────────┘
```

- **Barre gauche verte** = lane en lecture
- **Barre gauche orange** = lane en MANUAL WAIT (appuyer A ou B)
- **Barre gauche grise** = lane terminée

## Dépannage

| Symptôme | Solution |
|----------|----------|
| "WiFi failed" | Vérifier SSID/pass dans le sketch |
| "Server not found" | Vérifier l'IP et que D.I.M tourne sur un port entre 5000 et 5010 |
| Écran blanc au démarrage | Recompiler avec la bonne board sélectionnée |
