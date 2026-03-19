import sys
import os

# ── Gestion du bundle PyInstaller ────────────────────────────────────────────
# Quand l'exe est lancé, les assets sont dans sys._MEIPASS (dossier temporaire)
# On force le répertoire de travail sur ce chemin pour que tous les chemins
# relatifs (project.json, scenes/, images/…) fonctionnent dans le bundle.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    os.chdir(sys._MEIPASS)

import json
import system

if __name__ == "__main__":
    try:
        with open("project.json", "r", encoding="utf-8") as f:
            title = json.load(f)["config"].get("WINDOW_TITLE", "MEGADEMO")
    except Exception:
        title = "MEGADEMO"

    print(f"Lancement de {title} (Multipass Mode)...")
    app = system.Engine()
    app.run()
