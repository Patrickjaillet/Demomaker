"""
build_exe.py — Construit un exécutable standalone de la Megademo via PyInstaller.

Usage depuis la GUI (ExeExportDialog) ou en ligne de commande :
    python build_exe.py [--project-dir /chemin/vers/projet] [--output-dir /chemin/dist]

Prérequis :
    pip install pyinstaller

Ce script génère un .exe (Windows) ou un binaire Linux/macOS.
Il embarque : shaders, scènes, overlays, images, fonts, musique, project.json.
"""

import os
import sys
import json
import shutil
import subprocess
import argparse


def check_pyinstaller():
    """Vérifie si PyInstaller est disponible et retourne sa version."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return True, r.stdout.strip()
    except Exception:
        pass
    return False, "PyInstaller non trouvé. Installez-le : pip install pyinstaller"


def build_exe(project_dir: str,
              output_dir: str,
              on_log=None,
              on_progress=None,
              one_file: bool = True,
              console: bool = False):
    """
    Construit le .exe / binaire standalone.

    Args:
        project_dir  : chemin du dossier projet (contient main.py, project.json…)
        output_dir   : dossier de destination de la dist/
        on_log       : callable(str) pour les messages de log
        on_progress  : callable(str) pour les étapes
        one_file     : True = --onefile, False = --onedir
        console      : True = fenêtre console visible

    Returns:
        (True, exe_path) ou (False, message_erreur)
    """
    log      = on_log      or print
    progress = on_progress or (lambda s: None)

    # ── Vérifications préalables ─────────────────────────────────────────────
    ok, ver = check_pyinstaller()
    if not ok:
        return False, ver
    log(f"✔ PyInstaller {ver}")

    main_py = os.path.join(project_dir, "main.py")
    if not os.path.exists(main_py):
        return False, f"main.py introuvable dans {project_dir}"

    # Nom de l'exécutable depuis project.json
    pj_path  = os.path.join(project_dir, "project.json")
    exe_name = "megademo"
    try:
        with open(pj_path, "r", encoding="utf-8") as f:
            title = json.load(f)["config"].get("WINDOW_TITLE", "megademo")
            exe_name = title.lower().replace(" ", "_").replace("/", "-")[:32]
    except Exception:
        pass

    os.makedirs(output_dir, exist_ok=True)

    # ── Séparateur chemin PyInstaller (OS-dépendant) ─────────────────────────
    sep = ";" if sys.platform == "win32" else ":"

    # ── Assets à embarquer (source → destination dans le bundle) ─────────────
    # CORRIGÉ : "img" → "images" (dossier réel du projet)
    asset_pairs = [
        ("project.json",       "."),
        ("scenes",             "scenes"),
        ("overlays",           "overlays"),
        ("images",             "images"),   # logo, presents, album, etc.
        ("fonts",              "fonts"),
        ("music",              "music"),
        ("shaders",            "shaders"),
        ("AUDIO_REACTIVE.md",  "."),        # documentation optionnelle
    ]

    data_args = []
    for src_rel, dest in asset_pairs:
        full = os.path.join(project_dir, src_rel)
        if os.path.exists(full):
            data_args.extend(["--add-data", f"{full}{sep}{dest}"])
            log(f"  + data : {src_rel} → {dest}")
        else:
            log(f"  ⚠ asset ignoré (introuvable) : {src_rel}")

    # ── Hidden imports ────────────────────────────────────────────────────────
    # CORRIGÉ : ajout de audio_analysis, system, PIL, PySide6 si nécessaire
    hidden = [
        # Modules tiers
        "moderngl",
        "moderngl.mgl",
        "numpy",
        "numpy.core._methods",
        "numpy.core._multiarray_umath",
        "soundfile",
        "_soundfile_data",
        "pygame",
        "pygame.mixer",
        # Modules locaux du projet (PyInstaller ne les détecte pas toujours)
        "audio_analysis",
        "system",
        "viewport",
        "export_engine",
        # PIL (Pillow) — utilisé dans viewport.py pour charger les images overlay
        "PIL",
        "PIL.Image",
        "PIL.ImageOps",
    ]

    # ── Construction de la commande PyInstaller ───────────────────────────────
    progress("Préparation de la commande PyInstaller…")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",     exe_name,
        "--distpath", output_dir,
        "--workpath", os.path.join(output_dir, "_build_tmp"),
        "--specpath", os.path.join(output_dir, "_build_tmp"),
    ]

    if one_file:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    # CORRIGÉ : --noconsole fonctionne sur toutes les plateformes (PyInstaller 4+)
    if not console:
        cmd.append("--noconsole")

    for h in hidden:
        cmd += ["--hidden-import", h]

    cmd += data_args
    cmd.append(main_py)

    log("Commande :\n  " + " \\\n    ".join(cmd))

    # ── Lancement PyInstaller ─────────────────────────────────────────────────
    progress("Compilation en cours (peut prendre 1–2 minutes)…")
    log("▶ Démarrage PyInstaller…")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=project_dir,
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                log(line)
        proc.wait()
    except Exception as e:
        return False, f"Erreur lancement PyInstaller : {e}"

    if proc.returncode != 0:
        return False, f"PyInstaller a échoué (code {proc.returncode})"

    # ── Trouver le fichier produit ────────────────────────────────────────────
    if one_file:
        ext      = ".exe" if sys.platform == "win32" else ""
        exe_path = os.path.join(output_dir, exe_name + ext)
    else:
        exe_path = os.path.join(output_dir, exe_name)

    if not os.path.exists(exe_path):
        return False, f"Fichier produit introuvable : {exe_path}"

    size    = os.path.getsize(exe_path) if os.path.isfile(exe_path) else 0
    size_mb = size / (1024 * 1024) if size else 0
    log(f"✔ Exécutable : {exe_path}  ({size_mb:.1f} MB)")
    return True, exe_path


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build Megademo EXE via PyInstaller")
    ap.add_argument(
        "--project-dir",
        default=os.path.dirname(os.path.abspath(__file__)),
        help="Dossier du projet (contient main.py)")
    ap.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist"),
        help="Dossier de destination")
    ap.add_argument(
        "--onedir",
        action="store_true",
        help="Dossier au lieu d'un seul fichier exécutable")
    ap.add_argument(
        "--console",
        action="store_true",
        help="Garder la console visible")
    args = ap.parse_args()

    ok, result = build_exe(
        project_dir=args.project_dir,
        output_dir=args.output_dir,
        one_file=not args.onedir,
        console=args.console,
    )
    if ok:
        print(f"\n✔ Succès : {result}")
        sys.exit(0)
    else:
        print(f"\n✖ Échec : {result}")
        sys.exit(1)
