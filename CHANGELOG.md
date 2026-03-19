# CHANGELOG — MEGADEMO Demomaker

Toutes les modifications notables sont documentées ici.  
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/)  
Versionnage : [Semantic Versioning](https://semver.org/lang/fr/)

---

## [Unreleased]

### En cours
- Système de caméra 3D (`iCamMatrix` mat4, trajectoires)
- Particules GPU via Transform Feedback
- Intégration Blender live link
- Plugin API Python + SDK

---

## [3.0.0] — Phase 8 : Architecture & Performance

### Ajouté
- **`base_renderer.py`** — Classe de base `BaseRenderer` partagée par `Engine` et `ExportEngine`
  - Centralise : `_safe_set`, `_read_glsl`, `_write_png_raw`, `_make_prog`, `_get_prog` (cache),
    `_load_texture`, `_get_cached_texture`, `_scene_at`, `_overlay_at`,
    `_bind_audio_uniforms`, `_load_overlay_shader`, `release_base()`
  - Propriété `resolution` → `(width, height)` depuis `cfg["RES"]`
  - Constante `EMPTY_AUDIO_UNIFORMS` (20 uniforms à zéro)
  - Logger injectable via `_log`
- **`tests/`** — Suite pytest complète
  - `conftest.py` — Fixtures partagées : `project_dir`, `minimal_project`, `gl_context`,
    `base_renderer`, `audio_sine`, `audio_stereo`, `tmp_wav`, `small_png`
  - `test_base_renderer.py` — 25 tests (unit + gpu)
  - `test_audio_analysis.py` — 14 tests (unit + gpu + slow)
  - `test_export_engine.py` — 18 tests (unit + gpu + slow)
  - `test_project_config.py` — 12 tests (unit)
- **`pytest.ini`** — Configuration pytest avec marqueurs `unit`, `integration`, `slow`, `gpu`
- **`ARCHITECTURE.md`** — Diagrammes Mermaid : hiérarchie classes, pipeline GL,
  pipeline export, flux audio, couches logicielles, format project.json

### Modifié
- **`system.py`** — `Engine` hérite de `BaseRenderer`
  - Suppression des méthodes dupliquées (`load_texture`, `get_cached_texture`,
    `safe_set`, `_read_glsl`)
  - `_bind_audio_uniforms` délègue à `BaseRenderer` ; surcharge
    `_on_bind_audio_extra` pour textures GPU de l'analyseur + ParamSystem
  - `load_overlay_shader` délègue à `BaseRenderer._load_overlay_shader`
  - Initialisation GL via `self.init_gl_base(self.ctx)` après création du contexte Pygame
  - **Rétrocompatibilité totale** : API publique inchangée
- **`export_engine.py`** — `ExportEngine` hérite de `BaseRenderer`
  - Suppression des méthodes dupliquées (`_safe_set`, `_read_glsl`,
    `_get_texture`, `_write_png_raw`, `_scene_at`, `_overlay_at`)
  - `_make_prog` délègue à `BaseRenderer._make_prog`
  - `_load_overlay` délègue à `BaseRenderer._load_overlay_shader`
  - Initialisation GL via `self.init_gl_base(self.ctx)` dans `run()`
  - **Rétrocompatibilité totale** : API publique inchangée

### Supprimé
- Duplication de ~150 lignes entre `system.py` et `export_engine.py`

---

## [2.7.0] — Phase 7 : Export & Diffusion

### Ajouté
- **`ExportQueueDialog`** — File d'attente multi-exports avec progression globale
- **Rapport HTML automatique** après chaque export (`_generate_report()`)
  - résolution, FPS, codec, taille fichier, timestamp
- **Webhook POST-export** (`_send_webhook()`) — notification JSON Slack/Discord/custom

### Modifié
- `ExportEngine` : validation pre-export (assets, audio, shaders manquants)

---

## [2.6.0] — Phase 7 : Codecs & Séquences

### Ajouté
- Codec **H.265/HEVC** (`libx265`) avec tag `hvc1` (macOS compatible)
- Codec **ProRes 4444** (`prores_ks`)
- Codec **VP9** (`libvpx-vp9`)
- **Séquence PNG** (`png_seq`) — export frame par frame sans ffmpeg
- **Séquence EXR** (`exr_seq`) — 32 bits float ; fallback `.npy` si OpenEXR absent
- **CRF configurable** — curseur 0 (lossless) → 51 dans `Mp4ExportDialog`
- `_write_png_raw()` — écriture PNG RGB sans Pillow
- `ExportEngine.check_ffmpeg()` — détection ffmpeg dans le PATH

---

## [2.5.0] — Phase 7 : Export MP4 headless

### Ajouté
- `ExportEngine` — rendu moderngl standalone + encodage ffmpeg via pipe stdin
- `Mp4ExportDialog` — interface GUI (résolution, FPS, codec, CRF, chemin)
- Analyse audio offline via `AudioAnalyzer.precompute()` avant le rendu
- Menu **Export → Exporter en MP4…**

---

## [2.4.0] — Phase 6 : UI/UX & Ergonomie

### Ajouté
- **`ThemeManager`** — 5 thèmes intégrés : Neon Void, Cyber Amber, Synthwave Pink,
  High Contrast, Light Studio
- **Import `.theme.json`** + `ThemeDialog`
- **`CommandPalette`** — `Ctrl+P`, fuzzy search sur ~50 commandes
- **`KeymapEditor`** — raccourcis personnalisables, sauvegarde `keymap.json`
- **`MacroManager`** + `MacroDialog` — enregistrement et lecture de séquences
- **`LogPanel`** — logs structurés filtrables, export `.log`
- Viewports et Automation en fenêtre flottante (`Qt.Window`)
- Overlay debug audio (iKick/Bass/Mid/High/BPM) + mètre VU + indicateur FPS

---

## [2.3.0] — Phase 5 : Bibliothèque & Éditeur GLSL

### Ajouté
- **`ShaderBrowserPanel`** — grille `ShaderCard` avec thumbnails 160×90 (thread background)
- **`GlslEditorPanel`** — éditeur GLSL avec coloration syntaxique, panneau d'erreurs inline
- Hot-reload via `QFileSystemWatcher` par shader
- `validate_project_assets()` + `MissingAssetsDialog` + relink
- `DraggableAssetList` avec `QDrag`/`QMimeData`
- `ScenePresetManager` + presets `.preset.json`

---

## [2.2.0] — Phase 4 : Paramètres & Automation

### Ajouté
- Parser `// @param` — widgets auto-générés (float, int, bool, vec2, vec3, color)
- **`AutomationEditor`** — éditeur de courbes bézier
- 6 modes d'interpolation : Linear, Smooth, Step, Bounce, Elastic, EaseInOut
- **Enregistrement live** `⏺ REC` ~20 Hz
- LFO (sine/square/saw/triangle/random, sync BPM)
- `AudioModulator`, `MathNode`
- **GNU Rocket** — sync, import/export XML
- `AutomationCurve.copy_to()`

---

## [2.1.0] — Phase 3 : Timeline avancée

### Ajouté
- 4 types de pistes, multi-sélection, Copier/Coller, Dupliquer
- Snap magnétique, Trim gauche+droite, **Slip edit** (Ctrl+Shift+drag)
- Marqueurs nommés, régions de boucle/rendu, grille BPM
- Undo/Redo illimité, sauvegarde auto, versioning
- Import/Export `.democlip`

---

## [2.0.0] — Phase 2 : Système de Scènes & Pipeline GL

### Ajouté
- Config JSON par scène — champ `"passes"` dans `project.json`
- Jusqu'à 8 passes (A..H + main) avec résolution par passe
- **Passes conditionnelles** — `{"uniform":"iKick","op":">","threshold":0.5}`
- LUT strips `.raw`, textures de bruit précalculées
- **Feedback inter-scènes** — uniform `iPrevScene` (sampler2D)
- 6 shaders de transition : crossfade, glitch_cut, pixel_sort, ripple, wipe, zoom_blur
- Post-processing par scène : bloom, grain, vignette, LUT, saturation, contraste
- `TextureManager`, `TransitionManager`, `PostProcessor`

---

## [1.0.0] — Phase 1 : Moteur Audio Avancé

### Ajouté
- FFT adaptative 512/1024/2048/4096
- 24 bandes Bark critiques → texture `iBarkSpectrum`
- Largeur stéréo → `iStereoWidth`
- RMS vs Peak : `iBassPeak/RMS`, `iMidPeak/RMS`, `iHighPeak/RMS`
- Waterfall spectral → texture `iSpectrumHistory` (256×64)
- Beat tracking par autocorrélation → `BeatTracker`
- `iBar`, `iBeat4`, `iSixteenth`, `iSection`, `iEnergy`, `iDrop`
- Compensation de latence `LATENCY_MS`
- **Mode offline** `AudioAnalyzer.precompute()` avant l'export
- Cue points manuels `CUE_POINTS` → `iCue`

---

[Unreleased]: https://github.com/your-org/megademo/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/your-org/megademo/compare/v2.7.0...v3.0.0
[2.7.0]: https://github.com/your-org/megademo/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/your-org/megademo/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/your-org/megademo/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/your-org/megademo/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/your-org/megademo/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/your-org/megademo/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/your-org/megademo/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/your-org/megademo/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/your-org/megademo/releases/tag/v1.0.0
