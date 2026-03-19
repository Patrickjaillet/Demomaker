#version 330
// @param float iLatheSpeed  0.1  5.0  1.0
// @param float iRadius      0.2  2.0  0.8
// @param color iLaserColor  #ff4500
// @param float iGrainAmt    0.0  1.0  0.1
// CYBER LATHE — Scene shader (composite final)
// iChannel0 = Buffer A (tunnel 3D raymarché)
// iChannel1 = Buffer B (scan laser + grille + anneaux)
uniform sampler2D iChannel0;
uniform sampler2D iChannel1;
uniform sampler2D iChannel2;
uniform sampler2D iChannel3;
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
uniform float iTime;
out vec4 fragColor;

#define TAU 6.28318530718

vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }
float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.545); }

mat2 rot2(float a){ float c=cos(a),s=sin(a); return mat2(c,-s,s,c); }

void main(){
    vec2 uv  = gl_FragCoord.xy / iResolution.xy;
    vec2 c   = uv - 0.5;
    float r  = length(c);

    // ── Distorsion barrel + kick bulge ──────────────────────────────────────
    vec2 dc   = c * (1.0 + dot(c,c) * (0.15 + iKick * 0.25));
    vec2 uvd  = dc + 0.5;

    // ── Aberration chromatique radiale ──────────────────────────────────────
    float ca  = 0.004 + iKick * 0.016;
    vec2  dir = normalize(c + 0.001);
    vec3  geo;
    geo.r = texture(iChannel0, uvd + dir * ca * 1.5).r;
    geo.g = texture(iChannel0, uvd).g;
    geo.b = texture(iChannel0, uvd - dir * ca).b;

    // ── Overlay laser/grille ────────────────────────────────────────────────
    vec3 overlay = texture(iChannel1, uvd).rgb;

    // ── Bloom du tunnel ─────────────────────────────────────────────────────
    vec3 bloom = vec3(0.0);
    float wSum = 0.0;
    for(int i = -4; i <= 4; i++){
        for(int j = -4; j <= 4; j++){
            vec2 off = vec2(float(i), float(j)) / iResolution * 4.0;
            float wt = exp(-float(i*i + j*j) * 0.18);
            bloom += texture(iChannel0, uvd + off).rgb * wt;
            wSum += wt;
        }
    }
    bloom /= wSum;

    // ── Composite ───────────────────────────────────────────────────────────
    vec3 col = geo * 1.1
             + bloom * (0.5 + iKick * 1.4)
             + overlay * (0.8 + iKick * 1.0);

    // ── Glitch horizontal sur kick fort ─────────────────────────────────────
    float bigKick = smoothstep(0.6, 1.0, iKick);
    if(bigKick > 0.1){
        float glitchY  = floor(uv.y * 24.0);
        float glitchStr = hash(vec2(glitchY, floor(iTime * 24.0))) * bigKick;
        float xShift   = (hash(vec2(glitchY + 1.0, floor(iTime * 24.0))) - 0.5) * 0.05 * glitchStr;
        vec3 glitchSmp = texture(iChannel0, vec2(uvd.x + xShift, uvd.y)).rgb;
        col = mix(col, glitchSmp, glitchStr * 0.6);
    }

    // ── Scanlines CRT légères ────────────────────────────────────────────────
    float scan = 1.0 - 0.06 * sin(gl_FragCoord.y * 2.0);
    col *= scan;

    // ── Pulse flash central sur kick ────────────────────────────────────────
    float flash = exp(-r * (8.0 - iKick * 6.0)) * iKick * 0.4;
    col += vec3(0.0, 0.6, 1.0) * flash;

    // ── Vignette ────────────────────────────────────────────────────────────
    float vig = smoothstep(0.75, 0.25, r) * 0.7 + 0.3;
    col *= vig;

    // ── Grain numérique fin ──────────────────────────────────────────────────
    col += (hash(uv + fract(iTime * 1.37)) - 0.5) * 0.025;

    // ── Tone mapping ────────────────────────────────────────────────────────
    col = aces(col * 1.4);

    // ── Tint chaud sur kick (légère saturation orange) ──────────────────────
    float lum = dot(col, vec3(0.2126, 0.7152, 0.0722));
    col = mix(col, col * vec3(1.1, 0.95, 0.85), iKick * 0.3);

    // ── Transition fade in/out ──────────────────────────────────────────────
    float fade = smoothstep(0.0, 0.06, iSceneProgress) * smoothstep(1.0, 0.94, iSceneProgress);
    col *= fade;

    fragColor = vec4(col, 1.0);
}
