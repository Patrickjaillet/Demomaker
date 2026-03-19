#version 330
// CYBER LATHE — Buffer A
// Tunnel de barres métalliques rotatif avec pulse de kick percussif
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
uniform sampler2D iChannel0; // feedback
out vec4 fragColor;

#define PI  3.14159265359
#define TAU 6.28318530718

mat2 rot2(float a){ float c=cos(a),s=sin(a); return mat2(c,-s,s,c); }
float hash(float x){ return fract(sin(x*127.31)*43758.545); }
float hash2(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.545); }

// ── SDF : barre cylindrique orientée selon Z ────────────────────────────────
float sdCylZ(vec3 p, float r){
    return length(p.xy) - r;
}

// ── SDF : anneau torique ────────────────────────────────────────────────────
float sdTorus(vec3 p, vec2 t){
    vec2 q = vec2(length(p.xz) - t.x, p.y);
    return length(q) - t.y;
}

// ── Map : tunnel de barres + anneaux ────────────────────────────────────────
vec2 map(vec3 p){
    float t = iTime;

    // ── Rotation globale du tunnel ──
    float spinBase  = t * 0.4 + iKick * 0.8;
    float spinPulse = iKick * 1.5;
    p.xy = rot2(spinBase + spinPulse) * p.xy;

    // ── Barres périphériques : N barres sur un cercle ──────────────────────
    int   N      = 16;
    float radius = 2.2 + iKick * 0.4;
    float dBars  = 1e6;
    float matBars = 0.0;

    for(int i = 0; i < N; i++){
        float fi    = float(i);
        float angle = TAU * fi / float(N);
        // Phase individuelle sur beat
        float phase = hash(fi) * TAU;
        float wobble = sin(t * (1.5 + hash(fi+1.0)) + phase) * 0.25;
        wobble += iKick * (hash(fi+2.0) * 0.6 - 0.15);

        vec2 center = vec2(cos(angle), sin(angle)) * (radius + wobble);
        vec3 q = p;
        q.xy -= center;

        // Chaque barre a une épaisseur qui pulse au kick
        float r = 0.07 + 0.03 * sin(t * 3.0 + phase) + iKick * 0.06;
        float d = sdCylZ(q, r);
        if(d < dBars){
            dBars   = d;
            matBars = fi / float(N);
        }
    }

    // ── Barre centrale (axe du tunnel) ─────────────────────────────────────
    float dAxis = sdCylZ(p, 0.06 + iKick * 0.08);

    // ── Anneaux de renfort : répétés en Z ──────────────────────────────────
    vec3 pRing = p;
    float ringPeriod = 1.8;
    pRing.z = mod(p.z + ringPeriod * 0.5, ringPeriod) - ringPeriod * 0.5;
    float dRings = sdTorus(pRing.xzy, vec2(radius * 0.95, 0.04 + iKick * 0.03));

    // ── Union ──────────────────────────────────────────────────────────────
    float d = min(min(dBars, dAxis), dRings);
    float matId = (d == dBars) ? matBars : (d == dAxis ? -1.0 : -2.0);
    return vec2(d, matId);
}

// ── Normale par gradient ────────────────────────────────────────────────────
vec3 calcNormal(vec3 p){
    float e = 0.002;
    return normalize(vec3(
        map(p+vec3(e,0,0)).x - map(p-vec3(e,0,0)).x,
        map(p+vec3(0,e,0)).x - map(p-vec3(0,e,0)).x,
        map(p+vec3(0,0,e)).x - map(p-vec3(0,0,e)).x
    ));
}

void main(){
    vec2 uv  = (gl_FragCoord.xy - iResolution * 0.5) / iResolution.y;
    vec2 st  = gl_FragCoord.xy / iResolution.xy;

    // ── Caméra : avance dans le tunnel ─────────────────────────────────────
    float zoom  = 0.8 + iSceneProgress * 0.6;
    float speed = 1.2 + iKick * 0.8;
    vec3  ro    = vec3(0.0, 0.0, -iTime * speed);

    // Léger sway + secousse kick
    ro.xy += vec2(sin(iTime * 0.11) * 0.25, cos(iTime * 0.07) * 0.18);
    ro.xy += vec2(iKick * (hash2(vec2(floor(iTime*8.0), 0.0)) - 0.5),
                  iKick * (hash2(vec2(floor(iTime*8.0), 1.0)) - 0.5)) * 0.2;

    vec3  rd    = normalize(vec3(uv * zoom, 1.0));
    // Roll camera sur le beat
    rd.xy = rot2(iTime * 0.06 + iKick * 0.3) * rd.xy;

    // ── Raymarching ─────────────────────────────────────────────────────────
    float t    = 0.0;
    float tMax = 20.0;
    vec2  res  = vec2(1e6, 0.0);
    vec3  hitP = vec3(0.0);
    bool  hit  = false;

    for(int i = 0; i < 120; i++){
        vec3 p = ro + rd * t;
        vec2 h = map(p);
        if(h.x < 0.001){
            hit  = true;
            res  = h;
            hitP = p;
            break;
        }
        t += max(h.x * 0.6, 0.005);
        if(t > tMax) break;
    }

    vec3 col = vec3(0.0);

    if(hit){
        vec3 n = calcNormal(hitP);
        float matId = res.y;

        // ── Éclairage PBR simplifié ─────────────────────────────────────────
        // Lumière 1 : scan laser avant (cyan)
        vec3 ld1  = normalize(vec3(0.0, 0.0, 1.0));
        float d1  = max(dot(n, ld1), 0.0);
        // Lumière 2 : fill latérale (orange)
        vec3 ld2  = normalize(vec3(1.0, -0.5, 0.3));
        float d2  = max(dot(n, ld2), 0.0);

        // Spéculaire Blinn-Phong
        vec3  h3    = normalize(ld1 - rd);
        float spec  = pow(max(dot(n, h3), 0.0), 64.0);
        float spec2 = pow(max(dot(n, normalize(ld2-rd)), 0.0), 16.0);

        // Métal : couleur selon l'ID de barre (dégradé palette)
        vec3 baseColor;
        if(matId >= 0.0){
            // Barres : hue cyclique cyan → violet → orange
            float hue = matId;
            baseColor = 0.5 + 0.5 * cos(TAU * (vec3(0.0, 0.33, 0.67) + hue * 0.8));
            baseColor = mix(baseColor, vec3(0.6, 0.7, 0.8), 0.6); // métalliser
        } else if(matId == -1.0){
            baseColor = vec3(0.2, 0.8, 1.0); // axe cyan
        } else {
            baseColor = vec3(0.5, 0.5, 0.6); // anneaux chrome
        }

        col = baseColor * (d1 * 0.7 + d2 * 0.4 + 0.1);
        col += vec3(0.8, 1.0, 1.0) * spec  * (1.0 + iKick * 4.0);
        col += vec3(1.0, 0.5, 0.1) * spec2 * (0.5 + iKick * 1.5);

        // Fresnel rim light cyan sur les bords
        float fres = pow(1.0 - abs(dot(n, -rd)), 3.0);
        col += vec3(0.0, 0.8, 1.0) * fres * (0.5 + iKick * 1.0);

        // Atténuation distance
        col *= exp(-t * 0.05);
    }

    // ── Glow volumétrique sur le kick (émanant du centre) ──────────────────
    float r   = length(uv);
    float volG = exp(-r * (3.0 - iKick * 2.0)) * iKick * 0.6;
    col += vec3(0.1, 0.5, 1.0) * volG;

    // ── Feedback trail ─────────────────────────────────────────────────────
    vec2 fuv = st + rd.xy * 0.001;
    vec3 prev = texture(iChannel0, fuv).rgb * (0.78 - iKick * 0.2);
    col = max(col, prev);

    fragColor = vec4(col, t / tMax);
}
