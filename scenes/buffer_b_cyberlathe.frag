#version 330
// CYBER LATHE — Buffer B : Scan laser + grille holographique
uniform float iTime;
uniform vec2  iResolution;
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
uniform sampler2D iSpectrum;  // unit 8 — spectre log [0,1]
uniform sampler2D iWaveform;  // unit 9 — waveform  [0,1]
uniform float iSceneProgress;
uniform sampler2D iChannel0; // Buffer A
out vec4 fragColor;

#define TAU 6.28318530718

float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.545); }
float hash1(float x){ return fract(sin(x*127.31)*43758.545); }

mat2 rot2(float a){ float c=cos(a),s=sin(a); return mat2(c,-s,s,c); }

void main(){
    vec2 uv  = (gl_FragCoord.xy - iResolution * 0.5) / iResolution.y;
    vec2 st  = gl_FragCoord.xy / iResolution.xy;
    float ar = iResolution.x / iResolution.y;

    vec3 col = vec3(0.0);

    // ── Scan laser horizontal ───────────────────────────────────────────────
    // Une ligne de scan qui parcourt l'écran verticalement au tempo
    float scanSpeed = 1.8 + iKick * 0.5;
    float scanY     = fract(iTime * scanSpeed * 0.5 + iSceneProgress * 0.1);
    float scanDist  = abs(st.y - scanY);
    float scanLine  = exp(-scanDist * 120.0) * (0.6 + iKick * 1.5);
    col += vec3(0.0, 0.8, 1.0) * scanLine;

    // ── Grille holographique 3D (perspective) ──────────────────────────────
    // Projection perspective simple : grille qui file vers le centre
    vec2 grid = uv;
    grid = rot2(iTime * 0.05) * grid;

    // Grille perspective en Z
    float depth = 1.0 / (length(uv) + 0.1);
    float zOff  = iTime * 1.5 + iKick * 0.5;

    vec2 gridUV = grid * depth + vec2(0.0, zOff);
    gridUV *= 3.0;

    // Lignes de la grille
    vec2 gf = abs(fract(gridUV) - 0.5);
    float gridLine = min(gf.x, gf.y);
    float gridGlow = exp(-gridLine * 18.0);

    // Atténuation avec la distance au centre
    float radFade = exp(-length(uv) * 1.8);
    vec3 gridColor = mix(
        vec3(0.0, 0.5, 1.0),
        vec3(0.0, 1.0, 0.5),
        sin(gridUV.y * 0.5) * 0.5 + 0.5
    );
    col += gridColor * gridGlow * radFade * (0.15 + iKick * 0.35);

    // ── Anneaux de pulse concentriques sur kick ─────────────────────────────
    float r = length(uv);
    for(int i = 0; i < 5; i++){
        float fi   = float(i);
        // Chaque anneau part du centre à un moment différent
        float t0   = floor(iTime * 4.0) - fi;
        float age  = fract(iTime * 4.0 + fi * 0.25);
        float rad  = age * 1.2;
        float ring = exp(-abs(r - rad) * 30.0) * (1.0 - age);
        ring *= iKick;
        vec3 rc = mix(
            vec3(0.0, 1.0, 1.0),
            vec3(1.0, 0.3, 0.0),
            fi / 4.0
        );
        col += rc * ring * 0.8;
    }

    // ── Barres de données horizontales (effet techno) ───────────────────────
    for(int i = 0; i < 8; i++){
        float fi    = float(i);
        float yPos  = (fi / 8.0 - 0.5) * 1.6;
        float speed2 = 0.3 + hash1(fi) * 0.5;
        float xOff  = fract(iTime * speed2 + hash1(fi + 10.0));
        // Barre qui défile
        float barX  = st.x - xOff;
        float barLen = 0.05 + hash1(fi + 20.0) * 0.15;
        float onBar = step(0.0, barX) * step(barX, barLen);
        float yDist = abs(uv.y - yPos);
        float barGlow = exp(-yDist * 60.0) * onBar * (0.2 + iKick * 0.4);
        vec3 bc = vec3(hash1(fi)*0.3, 0.6 + hash1(fi+1.0)*0.4, 0.8 + hash1(fi+2.0)*0.2);
        col += bc * barGlow;
    }

    // ── Flash sur gros kick ─────────────────────────────────────────────────
    float bigKick = smoothstep(0.7, 1.0, iKick);
    col += vec3(0.0, 0.2, 0.4) * bigKick * 0.3;

    fragColor = vec4(col, 1.0);
}
