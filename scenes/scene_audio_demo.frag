/*  scene_audio_demo.frag
    ────────────────────────────────────────────────────────────────────────────
    Scène de démonstration : réaction audio sur tous les uniforms disponibles.
    ────────────────────────────────────────────────────────────────────────────

    UNIFORMS AUDIO DISPONIBLES DANS TOUS LES SHADERS
    ─────────────────────────────────────────────────
    float iKick      – énergie kick/sub-bass   [0..3]  lissée
    float iBass      – énergie basses (20-250 Hz)      [0..3]
    float iMid       – énergie médiums (250-4k Hz)     [0..3]
    float iHigh      – énergie aigus (4k-20k Hz)       [0..3]
    float iBeat      – impulsion percussive (onset)    [0..3]  décroit vite
    float iBPM       – BPM estimé en temps réel        [60..200]

    TEXTURES AUDIO GPU (1D, sampler2D, 1 ligne de hauteur)
    ───────────────────────────────────────────────────────
    sampler2D iSpectrum  – unit 8 : 256 bandes spectrales log [0,1]
    sampler2D iWaveform  – unit 9 : 512 samples de forme d'onde [0,1]

    UNIFORMS STANDARD (toujours présents)
    ──────────────────────────────────────
    float iTime          – temps absolu en secondes
    vec2  iResolution    – taille de la fenêtre
    float iSceneProgress – [0,1] progression dans la scène
*/

#version 330

// Standard
uniform float iTime;
uniform vec2  iResolution;
uniform float iSceneProgress;

// Audio scalaires
uniform float iKick;
uniform float iBass;
uniform float iMid;
uniform float iHigh;
uniform float iBeat;
uniform float iBPM;
uniform float iBassPeak;
uniform float iMidPeak;
uniform float iHighPeak;
uniform float iBassRMS;
uniform float iMidRMS;
uniform float iHighRMS;
uniform float iBar;
uniform float iBeat4;
uniform float iSixteenth;
uniform float iEnergy;
uniform float iDrop;
uniform float iStereoWidth;
uniform float iCue;
uniform float iSection;
uniform sampler2D iSpectrumHistory;
uniform sampler2D iBarkSpectrum;

// Audio textures
uniform sampler2D iSpectrum;   // unit 8 — 256 bandes log [0,1]
uniform sampler2D iWaveform;   // unit 9 — 512 samples  [0,1]

out vec4 fragColor;

// ── Helpers ──────────────────────────────────────────────────────────────────

mat2 rot2(float a){ float c=cos(a),s=sin(a); return mat2(c,-s,s,c); }

float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }

float noise(vec2 p){
    vec2 i=floor(p), f=fract(p);
    f=f*f*(3.0-2.0*f);
    return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),
               mix(hash(i+vec2(0,1)),hash(i+vec2(1)),f.x),f.y);
}

// Palette HSL rapide
vec3 hsl(float h, float s, float l){
    vec3 rgb = clamp(abs(mod(h*6.0+vec3(0,4,2),6.0)-3.0)-1.0, 0.0, 1.0);
    return l + s*(rgb - 0.5)*(1.0 - abs(2.0*l - 1.0));
}

// ── Spectre en bas de l'écran ─────────────────────────────────────────────────

vec4 drawSpectrum(vec2 uv){
    if(uv.y > 0.15) return vec4(0.0);
    float y = uv.y / 0.15;
    float amp = texture(iSpectrum, vec2(uv.x, 0.5)).r;
    float bar = step(y, amp);
    vec3 col = hsl(uv.x * 0.7 + iTime*0.05, 0.9, 0.5);
    return vec4(col * bar, bar * 0.85);
}

// ── Waveform au milieu ────────────────────────────────────────────────────────

vec4 drawWaveform(vec2 uv){
    float band = 0.04;
    float cy   = 0.5;
    if(abs(uv.y - cy) > band) return vec4(0.0);

    float sample = texture(iWaveform, vec2(uv.x, 0.5)).r * 2.0 - 1.0;
    float wave_y = cy + sample * 0.08 * (1.0 + iBass * 2.0);
    float d = abs(uv.y - wave_y);
    float line = smoothstep(0.006, 0.0, d);
    vec3 col = mix(vec3(0.0, 0.8, 1.0), vec3(1.0, 0.2, 0.6), uv.x);
    return vec4(col * line, line);
}

// ── Fond : particules pulsantes ───────────────────────────────────────────────

vec3 background(vec2 uv, float t){
    vec2 c = uv - 0.5;
    c *= rot2(t * 0.05 + iBass * 0.2);

    float bpm_phase = mod(t * iBPM / 60.0, 1.0);
    float pulse  = exp(-bpm_phase * 4.0) * iBeat;

    // Grille pulsante sur le BPM
    vec2 grid = fract(c * (6.0 + iBass * 3.0) + t * 0.1) - 0.5;
    float g = smoothstep(0.06, 0.0, length(grid)) * (0.3 + pulse);

    // Ondes concentriques sur le kick
    float r = length(c);
    float rings = 0.5 + 0.5*sin(r * 30.0 - t * 4.0 + iKick * 6.0);
    rings *= exp(-r * 3.0) * iKick;

    // Brouillard médiums
    float fog = noise(c * 3.0 + t * 0.3) * iMid * 0.4;

    vec3 col = hsl(r + t * 0.1, 0.8, 0.15);
    col += hsl(0.6 + iMid * 0.3, 1.0, 0.5) * g;
    col += hsl(0.1, 1.0, 0.6) * rings;
    col += hsl(0.55 + iHigh * 0.2, 0.7, 0.4) * fog;

    // Flash blanc sur beat fort
    col += pulse * 0.4;
    return col;
}

// ── Main ──────────────────────────────────────────────────────────────────────

void main(){
    vec2 uv  = gl_FragCoord.xy / iResolution.xy;
    vec2 uvC = uv - 0.5;

    // Distortion d'écran sur kick
    float kick_warp = iKick * 0.015;
    uv  += uvC * kick_warp;
    uv   = clamp(uv, 0.0, 1.0);

    // Fond
    vec3 col = background(uv, iTime);

    // Waveform (alpha blending)
    vec4 wv = drawWaveform(uv);
    col = mix(col, wv.rgb, wv.a);

    // Spectre (alpha blending)
    vec4 sp = drawSpectrum(uv);
    col = mix(col, sp.rgb, sp.a);

    // Aberration chromatique sur les aigus
    float ca = iHigh * 0.008;
    col.r = mix(col.r, background(uv + vec2(ca, 0.0), iTime).r, 0.4);
    col.b = mix(col.b, background(uv - vec2(ca, 0.0), iTime).b, 0.4);

    // Vignette
    col *= 1.0 - smoothstep(0.4, 0.85, length(uvC));

    // Fade in/out de scène
    float fade = smoothstep(0.0, 0.04, iSceneProgress) * smoothstep(1.0, 0.96, iSceneProgress);
    col *= fade;

    fragColor = vec4(col, 1.0);
}
