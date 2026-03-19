#version 330
// GRID STORM — Buffer A
// Génère la grille hexagonale pulsée + champ de distance pour le scene shader
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

#define PI 3.14159265359
#define TAU 6.28318530718

// ── Noise ───────────────────────────────────────────────────────────────────
float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
float hash1(float x){ return fract(sin(x*127.31)*43758.545); }

vec2 hexCell(vec2 p){
    // Hexagonal tiling: renvoie coord dans la cellule hex + ID
    const vec2 s = vec2(1.0, 1.732050808);
    vec4 hC = floor(vec4(p, p - vec2(0.5, 1.0)) / s.xyxy) + 0.5;
    vec4 h  = vec4(p - hC.xy * s, p - (hC.zw + 0.5) * s);
    return (dot(h.xy, h.xy) < dot(h.zw, h.zw)) ? h.xy : h.zw;
}

vec2 hexId(vec2 p){
    const vec2 s = vec2(1.0, 1.732050808);
    vec4 hC = floor(vec4(p, p - vec2(0.5, 1.0)) / s.xyxy) + 0.5;
    vec4 h  = vec4(p - hC.xy * s, p - (hC.zw + 0.5) * s);
    return (dot(h.xy, h.xy) < dot(h.zw, h.zw)) ? hC.xy : hC.zw;
}

// ── SDF hexagone ────────────────────────────────────────────────────────────
float sdHex(vec2 p, float r){
    p = abs(p);
    return max(dot(p, normalize(vec2(1.0, 1.732))), p.x) - r;
}

// ── Raymarching: grille 3D ──────────────────────────────────────────────────
mat2 rot2(float a){ float c=cos(a),s=sin(a); return mat2(c,-s,s,c); }

float mapGrid(vec3 p){
    // Couche hexagonale répétée en profondeur
    float scale = 3.5 + iKick * 1.2;
    vec2 uv = p.xy * scale;

    // Rotation lente + secousse sur kick
    float angle = iTime * 0.08 + iKick * 0.4;
    uv = rot2(angle) * uv;

    vec2 cell = hexCell(uv);
    vec2 id   = hexId(uv);

    // Hauteur de chaque hex animée individuellement
    float phase = hash(id) * TAU;
    float freq  = 0.5 + hash(id + 0.1) * 1.5;
    float h     = sin(iTime * freq + phase) * 0.5 + 0.5;
    h = h + iKick * (0.3 + hash(id + 0.3) * 0.7);

    // Colonne hex : plan en z
    float rim  = sdHex(cell, 0.42);
    float col3d = max(rim, abs(p.z - h * 2.0) - (0.15 + h * 0.4));

    // Répétition Z des dalles
    vec3 q = p;
    q.z = mod(p.z + 2.0, 4.0) - 2.0;
    float plane = abs(q.z) - 0.04;

    return min(col3d, plane);
}

void main(){
    vec2 uv = (gl_FragCoord.xy - iResolution * 0.5) / iResolution.y;

    // Camera orbit + plonge sur kick
    float camZ = -4.0 + iSceneProgress * 1.5;
    vec3 ro = vec3(0.0, 0.0, camZ);
    ro.xy  += vec2(sin(iTime*0.07), cos(iTime*0.05)) * 0.3;

    // Caméra secouée sur kick
    ro.y += iKick * 0.15;

    vec3 rd = normalize(vec3(uv * (1.0 + iKick * 0.08), 1.0));
    rd.xy = rot2(iTime * 0.04) * rd.xy;

    // Raymarch
    float t = 0.0;
    float minD = 1e6;
    vec3  hitNorm = vec3(0.0);
    vec3  hitP    = vec3(0.0);
    bool  hit     = false;

    for(int i = 0; i < 80; i++){
        vec3 p = ro + rd * t;
        float d = mapGrid(p);
        minD = min(minD, d);
        if(d < 0.002){
            hit  = true;
            hitP = p;
            // Gradient normal
            float e = 0.002;
            hitNorm = normalize(vec3(
                mapGrid(p+vec3(e,0,0)) - mapGrid(p-vec3(e,0,0)),
                mapGrid(p+vec3(0,e,0)) - mapGrid(p-vec3(0,e,0)),
                mapGrid(p+vec3(0,0,e)) - mapGrid(p-vec3(0,0,e))
            ));
            break;
        }
        t += max(d * 0.5, 0.005);
        if(t > 14.0) break;
    }

    vec3 col = vec3(0.0);
    if(hit){
        // Éclairage: deux lumières de couleurs cyberpunk
        vec3 ld1 = normalize(vec3( 1.0,  1.0, -1.0));
        vec3 ld2 = normalize(vec3(-1.0, -0.5,  0.5));

        float diff1 = max(dot(hitNorm, ld1), 0.0);
        float diff2 = max(dot(hitNorm, ld2), 0.0);

        vec3 c1 = vec3(0.0, 0.9, 1.0); // cyan
        vec3 c2 = vec3(1.0, 0.3, 0.0); // orange

        // Fresnel
        float fres = pow(1.0 - abs(dot(hitNorm, -rd)), 3.0);
        float spec1 = pow(max(dot(reflect(-ld1, hitNorm), -rd), 0.0), 24.0);

        col = c1 * diff1 * 0.7
            + c2 * diff2 * 0.5
            + c1 * spec1 * (1.5 + iKick * 3.0)
            + c1 * fres  * (0.4 + iKick * 0.6)
            + vec3(0.0, 0.2, 0.4) * 0.1; // ambient

        // Profondeur AO grossière
        col *= 1.0 - t * 0.04;
    }

    // Glow ambiant sur les arêtes (champ de distance proche = glow)
    float edgeGlow = exp(-minD * 18.0) * (0.3 + iKick * 0.8);
    col += vec3(0.0, 1.0, 1.0) * edgeGlow * 0.5;
    col += vec3(1.0, 0.4, 0.0) * edgeGlow * edgeGlow * 0.3;

    // Feedback pour motion blur
    vec2 fuv = gl_FragCoord.xy / iResolution.xy;
    fuv += rd.xy * 0.001;
    vec3 prev = texture(iChannel0, fuv).rgb * (0.82 - iKick * 0.15);
    col = max(col, prev);

    fragColor = vec4(col, 1.0);
}
