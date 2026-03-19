# AUDIO REACTIVE — Référence GLSL
## Uniforms disponibles dans tous les shaders

### Scalaires audio (float)

| Uniform   | Plage    | Description                                         |
|-----------|----------|-----------------------------------------------------|
| `iKick`   | [0..3]   | Énergie kick / sub-bass (20–150 Hz), lissée         |
| `iBass`   | [0..3]   | Basses (20–250 Hz), lissée                          |
| `iMid`    | [0..3]   | Médiums (250–4000 Hz), lissée                       |
| `iHigh`   | [0..3]   | Aigus (4000–20000 Hz), lissée                       |
| `iBeat`   | [0..3]   | Impulsion percussive (onset flux), décroissance rapide |
| `iBPM`    | [60..200]| BPM estimé en temps réel                            |

### Textures GPU (sampler2D, 1D — 1 pixel de hauteur)

| Uniform      | Unit | Taille   | Description                                    |
|--------------|------|----------|------------------------------------------------|
| `iSpectrum`  | 8    | 256×1 f  | Spectre log (20 Hz → Nyquist), normalisé [0,1] |
| `iWaveform`  | 9    | 512×1 f  | Forme d'onde courante, remappée [0,1]          |

### Uniforms standard (inchangés)

| Uniform          | Type    | Description                                  |
|------------------|---------|----------------------------------------------|
| `iTime`          | float   | Temps absolu en secondes                     |
| `iResolution`    | vec2    | Taille de la fenêtre (px)                    |
| `iSceneProgress` | float   | Progression [0,1] dans la scène courante     |
| `iChannel0..3`   | sampler2D | Buffers multipass (A, B, C, D)            |

---

## Exemples d'utilisation GLSL

```glsl
// Déclaration (ajouter en tête de shader)
uniform float iKick;
uniform float iBass;
uniform float iMid;
uniform float iHigh;
uniform float iBeat;
uniform float iBPM;
uniform sampler2D iSpectrum;  // unit 8
uniform sampler2D iWaveform;  // unit 9

// --- Utilisation ---

// Zoom sur le kick
float zoom = 1.0 + iKick * 0.05;
vec2 uv_zoomed = (uv - 0.5) / zoom + 0.5;

// Couleur qui change avec les médiums
vec3 col = mix(vec3(0,0,1), vec3(1,0,0), iMid);

// Pulse synchronisé sur le BPM
float bpm_phase = mod(iTime * iBPM / 60.0, 1.0);
float pulse = exp(-bpm_phase * 5.0) * iBeat;

// Lire le spectre (x = fréquence log 0→1)
float amp = texture(iSpectrum, vec2(uv.x, 0.5)).r;

// Lire la forme d'onde (x = position temporelle 0→1)
float wave = texture(iWaveform, vec2(uv.x, 0.5)).r * 2.0 - 1.0;

// Aberration chromatique sur les aigus
float ca = iHigh * 0.01;
col.r = texture(iChannel0, uv + vec2(ca, 0)).r;
col.b = texture(iChannel0, uv - vec2(ca, 0)).b;
```

---

## Configuration (project.json → config)

```json
"KICK_SENS":       1.5,   // sensibilité globale kick (multiplicateur)
"AUDIO_SMOOTHING": 0.85   // lissage temporel [0=brutal, 1=très lisse]
```

---

## Notes techniques

- Les textures `iSpectrum` / `iWaveform` sont déclarées optionnelles :  
  le moteur ne les envoie que si l'uniform est présent dans le shader  
  (détecté via `name in prog`).  
- `iKick` reste rétrocompatible avec les shaders existants.  
- Le lissage `AUDIO_SMOOTHING` s'applique à `iKick`, `iBass`, `iMid`, `iHigh`.  
  `iBeat` a sa propre décroissance rapide (onset detector).
