# MEGADEMO — Architecture

> **Version :** Phase 8  
> **Diagrammes :** Mermaid  
> **Mise à jour :** 2025

---

## Vue d'ensemble

MEGADEMO est un moteur de démoscène écrit en Python, articulé autour de :

- un **pipeline de rendu GLSL** configurable par JSON  
- un **analyseur audio réactif** temps-réel et offline  
- une **GUI PyQt6** avec timeline, automation de courbes, éditeur GLSL  
- un **moteur d'export headless** (MP4, ProRes, séquences PNG/EXR)

---

## Arborescence des fichiers

```
megademo/
├── base_renderer.py      ← NOUVEAU Phase 8 : base partagée Engine + ExportEngine
├── system.py             ← Moteur temps-réel (hérite BaseRenderer)
├── export_engine.py      ← Moteur export (hérite BaseRenderer)
├── pipeline.py           ← ScenePipeline, TextureManager, TransitionManager, PostProcessor
├── audio_analysis.py     ← AudioAnalyzer (FFT, BPM, Bark, waterfall)
├── param_system.py       ← ParamSystem, AutomationCurve, LFO
├── demomaker_gui.py      ← Fenêtre principale PyQt6
├── viewport.py           ← Widget OpenGL temps-réel
├── automation_widget.py  ← Éditeur de courbes bézier
├── build_exe.py          ← Empaquetage PyInstaller
├── project.json          ← Données du projet courant
├── scenes/               ← Shaders GLSL par scène  (scene_*.frag, buffer_*.frag)
├── overlays/             ← Shaders d'overlay
├── shaders/              ← Shaders système (intro, transition, post-process)
├── fonts/                ← Polices (fabric-shapes.ttf…)
├── images/               ← Textures d'intro (logo, presents, album)
├── luts/                 ← LUT strips .raw
├── noise/                ← Textures de bruit .raw
├── export/               ← Vidéos exportées
└── tests/                ← Suite pytest
    ├── test_base_renderer.py
    ├── test_audio_analysis.py
    ├── test_export_engine.py
    └── test_project_config.py
```

---

## Hiérarchie des classes (Phase 8)

```mermaid
classDiagram
    class BaseRenderer {
        +project_dir: str
        +cfg: dict
        +timeline: list
        +overlays: list
        +ctx: moderngl.Context
        +_quad_buf: Buffer
        +_prog_cache: dict
        +_tex_cache: dict
        +init_gl_base(ctx)
        +_safe_set(prog, name, value)$
        +_read_glsl(path)$
        +_write_png_raw(path, arr)$
        +_make_prog(frag_code)
        +_get_prog(key, frag_code)
        +_load_texture(path)
        +_get_cached_texture(rel_path)
        +_scene_at(t)
        +_overlay_at(t)
        +_bind_audio_uniforms(prog, uniforms)
        +_on_bind_audio_extra(prog, uniforms, scene, t)
        +_load_overlay_shader(effect_name)
        +release_base()
        +resolution: tuple
    }

    class Engine {
        +analyzer: AudioAnalyzer
        +param_system: ParamSystem
        +_texmgr: TextureManager
        +_transition: TransitionManager
        +_post: PostProcessor
        +audio_uniforms: dict
        +run()
        +_on_bind_audio_extra()
        +_load_scene(sc, t)
        +_render_timeline(t, res)
        +_render_overlay(t, res)
    }

    class ExportEngine {
        +width: int
        +height: int
        +fps: int
        +codec: str
        +crf: int
        +run(output_path)
        +cancel()
        +_load_audio()
        +_get_audio_uniforms(frame_idx)
        +_run_sequence(output_dir, total_frames)
        +check_ffmpeg()$
    }

    BaseRenderer <|-- Engine
    BaseRenderer <|-- ExportEngine
```

---

## Pipeline GL par scène

```mermaid
flowchart LR
    Audio([AudioAnalyzer]) -->|uniforms| BindAudio

    subgraph ScenePipeline
        BufferA["Buffer A\nbuffer_a_*.frag\n(feedback optionnel)"]
        BufferB["Buffer B\nbuffer_b_*.frag"]
        BufferC["Buffer C\nbuffer_c_*.frag"]
        BufferD["Buffer D\nbuffer_d_*.frag"]
        Main["Main Pass\nscene_*.frag"]
    end

    BufferA -->|tex_A| BufferB
    BufferA -->|tex_A| BufferC
    BufferB -->|tex_B| BufferC
    BufferC -->|tex_C| BufferD
    BufferB -->|tex_B| BufferD
    BufferD -->|tex_D| Main
    BufferB -->|tex_B| Main
    BufferC -->|tex_C| Main

    Main --> PostProcessor["PostProcessor\nbloom · grain · vignette\nLUT · saturation · contraste"]
    PostProcessor --> FBO["FBO / Écran"]
    BindAudio --> ScenePipeline
```

---

## Pipeline Export

```mermaid
sequenceDiagram
    participant GUI as GUI (QThread)
    participant EE  as ExportEngine
    participant AA  as AudioAnalyzer
    participant GL  as moderngl (headless)
    participant FF  as ffmpeg (subprocess)

    GUI->>EE: run(output_path)
    EE->>GL: create_standalone_context()
    EE->>AA: precompute(duration, fps)
    AA-->>EE: _audio_frames[0..N]
    EE->>FF: Popen(["ffmpeg", ...], stdin=PIPE)

    loop frame 0..N
        EE->>GL: render passes (A/B/C/D/main)
        GL-->>EE: raw pixels (RGB bytes)
        EE->>FF: stdin.write(pixels)
        EE->>GUI: on_progress(frame, total)
    end

    EE->>FF: stdin.close()
    FF-->>EE: returncode
    EE-->>GUI: True / False
```

---

## Flux de données audio

```mermaid
flowchart TD
    WAV[Fichier audio WAV/OGG/FLAC]
    WAV --> SF[soundfile.read]
    SF --> PCM[PCM float32 mono + stéréo]

    subgraph AudioAnalyzer
        PCM --> FFT["FFT adaptative\n512/1024/2048/4096"]
        FFT --> Bands["24 bandes Bark\niSpectrum · iBarkSpectrum"]
        FFT --> Beat["BeatTracker\niBPM · iBar · iBeat4 · iSixteenth"]
        PCM --> Stereo["Largeur stéréo\niStereoWidth"]
        Bands --> Energy["RMS / Peak\niKick · iBass · iMid · iHigh\niEnergy · iDrop"]
        FFT --> Waterfall["Waterfall 256×64\niSpectrumHistory"]
        FFT --> Waveform["Waveform 512×1\niWaveform"]
    end

    Energy --> UniformsDict[dict uniforms scalaires]
    Bands  --> TexturesGPU[Textures GPU sampler2D]
    Waterfall --> TexturesGPU
    Waveform  --> TexturesGPU
    UniformsDict --> Shader[Fragment Shader]
    TexturesGPU  --> Shader
```

---

## Couches logicielles

```mermaid
graph TD
    subgraph UI["Couche UI (PyQt6)"]
        GUI[demomaker_gui.py]
        VP[viewport.py]
        AW[automation_widget.py]
    end

    subgraph Engine["Couche Moteur"]
        BR[base_renderer.py]
        SY[system.py]
        EE[export_engine.py]
        PL[pipeline.py]
    end

    subgraph Audio["Couche Audio"]
        AA[audio_analysis.py]
        PS[param_system.py]
    end

    subgraph GL["Couche GPU"]
        MGL[moderngl]
        GLSL[Shaders GLSL]
    end

    GUI --> SY
    GUI --> EE
    VP  --> SY
    SY  --> BR
    EE  --> BR
    BR  --> MGL
    SY  --> PL
    PL  --> MGL
    PL  --> GLSL
    SY  --> AA
    EE  --> AA
    SY  --> PS
```

---

## Format `project.json` — champs principaux

| Champ | Type | Description |
|-------|------|-------------|
| `config.RES` | `[int, int]` | Résolution de rendu `[width, height]` |
| `config.MUSIC_FILE` | `string` | Chemin relatif vers l'audio |
| `config.MUSIC_DURATION` | `float` | Durée totale en secondes |
| `config.BPM` | `float` | BPM de référence (override auto-détection) |
| `config.CUE_POINTS` | `float[]` | Cue points manuels → `iCue` |
| `config.automation` | `object` | Données d'automation par scène |
| `timeline[].base_name` | `string` | Nom de la scène (→ `scenes/scene_<name>.frag`) |
| `timeline[].start` | `float` | Début en secondes |
| `timeline[].duration` | `float` | Durée en secondes |
| `timeline[].passes` | `array` | Config passes (optionnel, défaut A/B/C/D) |
| `timeline[].post` | `object` | Post-processing : `bloom`, `grain`, `vignette`, `lut`… |
| `timeline[].transition_in` | `object` | `{effect, duration}` |
| `overlays[].effect` | `string` | Nom du shader overlay |
| `overlays[].file` | `string` | Texture ou `"SCROLL_INTERNAL"` |

---

## Dépendances externes

| Package | Usage |
|---------|-------|
| `moderngl` | Contexte OpenGL, textures, FBO, programmes GLSL |
| `pygame` | Fenêtre OS, mixer audio, chargement d'images (fallback) |
| `numpy` | Calculs DSP, buffers pixel, FFT |
| `soundfile` | Lecture audio PCM (WAV / OGG / FLAC) |
| `PyQt6` | Interface graphique complète |
| `Pillow` *(optionnel)* | Chargement textures PNG dans l'export headless |
| `OpenEXR` *(optionnel)* | Export séquences EXR 32 bits |
| `mido` *(optionnel)* | Réception MIDI live |
| `ffmpeg` *(PATH)* | Encodage vidéo MP4 / H.265 / ProRes / VP9 |

---

## Conventions de nommage des shaders

```
scenes/
  scene_<name>.frag       ← Pass principale
  buffer_a_<name>.frag    ← Pass A (feedback optionnel)
  buffer_b_<name>.frag    ← Pass B
  buffer_c_<name>.frag    ← Pass C
  buffer_d_<name>.frag    ← Pass D
overlays/
  <effect>.frag           ← Shader d'overlay
shaders/
  transition_<name>.frag  ← Transitions (crossfade, glitch_cut, …)
  post.frag               ← Post-processing
  intro.frag              ← Écran d'intro
```

---

## Uniforms système injectés automatiquement

| Uniform | Type | Description |
|---------|------|-------------|
| `iTime` | `float` | Temps global en secondes |
| `iResolution` | `vec2` | Résolution en pixels |
| `iSceneProgress` | `float` | Progression `[0, 1]` dans la scène |
| `iChannel0..3` | `sampler2D` | Textures des passes précédentes |
| `iPrevScene` | `sampler2D` | Dernière frame de la scène précédente |
| `iKick`, `iBass`, `iMid`, `iHigh` | `float` | Énergie audio par bande |
| `iBPM`, `iBar`, `iBeat4` | `float` | Rythme |
| `iSpectrum` | `sampler2D` | Spectre log 256×1 |
| `iBarkSpectrum` | `sampler2D` | 24 bandes Bark |
| `iSpectrumHistory` | `sampler2D` | Waterfall 256×64 |
| `iWaveform` | `sampler2D` | Forme d'onde 512×1 |

---

*Document généré automatiquement par la Phase 8 — Architecture & Performance.*
