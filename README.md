# Demomaker — Architecture

> **Version : 1.0 
> **Mise à jour : 19/03/2026

---

## Vue d'ensemble

Demomaker est un moteur de démoscène écrit en Python, articulé autour de :

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
