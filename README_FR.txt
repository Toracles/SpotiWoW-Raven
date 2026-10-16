# SpotiWoW-Raven v1.4.7 — Français

SpotiWoW-Raven relie Spotify à compatible WoW 1.12.1 client via le bridge de fichiers SuperWoW. Cette version utilise l’interface et les messages en français.

## Installation simple
1. Télécharge `SpotiWoW-Raven-Setup.exe` depuis la page **Releases** du dépôt GitHub officiel.
2. Ferme Turtle WoW avant l’installation.
3. Choisis `Français (FR)` dans l’installateur, sélectionne le dossier contenant `VanillaFixes.exe`, puis colle ton Spotify Client ID.
4. Dans les paramètres de ton application Spotify Developer, ajoute le Redirect URI exact `http://127.0.0.1:8888/callback`.
5. Termine l’installation puis lance **SpotiWoW-Raven** depuis le raccourci créé.

L’installateur ne demande jamais de Client Secret et ne télécharge pas Turtle WoW, VanillaFixes, SuperWoW, SuperAPI ni leurs DLL.

## Prérequis
- Client compatible WoW 1.18.1 client basé sur WoW 1.12.1.
- SuperWoW avec les fonctions `ImportFile` et `ExportFile`.
- `VanillaFixes.exe` présent dans le dossier du client.
- Une application Spotify Developer configurée avec le Redirect URI indiqué ci-dessus.

## Fonctionnalités
- Raccourci `Ctrl+Alt+L` pour activer/désactiver Lyrics depuis le compagnon, sans saisir de commande dans le chat.
- Message `Mode Lyrics : ON/OFF` affiché localement dans la fenêtre de chat via `DEFAULT_CHAT_FRAME:AddMessage`. Aucun message de statut n’est envoyé aux autres joueurs.
- Mini-lecteur et contrôles Spotify.
- Recherche de paroles horodatées multi-sources et cache local.
- Lanceur de zone de notification Windows sans console CMD visible.
- Arrêt automatique du bridge lorsque le processus du client `WoW.exe` se ferme, y compris avec Alt+F4.

Les paroles elles-mêmes restent envoyées dans le canal choisi si cette option est activée. Les noms techniques `SpotifyNowDB`, `SpotifyNowState.txt` et `SpotifyNowCommand.txt` sont conservés pour la compatibilité.

## Dépannage
- Journaux : `logs/bridge.log` et `logs/launcher.log` dans le dossier de l’application compagnon.
- Si aucun dossier n’est détecté, sélectionne manuellement celui qui contient `VanillaFixes.exe`.

Pour une mise à jour de l’addon uniquement, télécharge `SpotiWoW-Raven-Addon-FR.zip` depuis les Releases. La version française affiche les messages système en français.
