/*  post_process.frag  —  Phase 2.4 : Post-processing global
    =========================================================
    iChannel0  : rendu de la scène
    iPostBloom : intensité bloom  [0..2]
    iPostGrain : intensité grain  [0..1]
    iPostVig   : intensité vignette [0..1]
    iPostSat   : saturation       [0..2]  (1 = neutre)
    iPostContrast : contraste     [0..2]  (1 = neutre)
    iPostLUT   : 0 = désactivé, 1 = applique iChannel1 comme LUT strip 256×1
*/
#version 330

uniform sampler2D iChannel0;   // scène rendue
uniform sampler2D iChannel1;   // LUT strip  (256×1 si activé)
uniform vec2      iResolution;
uniform float     iTime;
uniform float     iPostBloom;
uniform float     iPostGrain;
uniform float     iPostVig;
uniform float     iPostSat;
uniform float     iPostContrast;
uniform float     iPostLUT;    // 0 ou 1
// Audio
uniform float     iKick;
uniform float     iBass;
uniform float     iEnergy;

out vec4 fragColor;

// ── Helpers ──────────────────────────────────────────────────────────────────
float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }

vec3 aces(vec3 x){
    return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14), 0.0, 1.0);
}

// LUT strip 256×1 : R→X, G→Y, B→Z (look-up 1D indépendant par canal)
vec3 applyLUT(vec3 col){
    col.r = texture(iChannel1, vec2(col.r, 0.5)).r;
    col.g = texture(iChannel1, vec2(col.g, 0.5)).g;
    col.b = texture(iChannel1, vec2(col.b, 0.5)).b;
    return col;
}

// ── Bloom simple (3 passes de blur horizontal+vertical) ──────────────────────
vec3 bloom(vec2 uv, float strength){
    if(strength < 0.01) return vec3(0.0);
    vec2 texel = 1.0 / iResolution;
    vec3 acc   = vec3(0.0);
    float tot  = 0.0;
    for(int i = -4; i <= 4; i++){
        for(int j = -4; j <= 4; j++){
            float w = exp(-float(i*i + j*j) * 0.18);
            acc += texture(iChannel0, uv + vec2(i,j)*texel*3.0).rgb * w;
            tot += w;
        }
    }
    acc /= tot;
    // Ne garder que les hautes lumières
    vec3 bright = max(acc - 0.6, 0.0);
    return bright * strength;
}

// ── Grain cinématique ─────────────────────────────────────────────────────────
float grain(vec2 uv, float t, float str){
    if(str < 0.001) return 0.0;
    float n = hash(uv * iResolution + fract(t * 47.3));
    return (n - 0.5) * str;
}

// ── Vignette ─────────────────────────────────────────────────────────────────
float vignette(vec2 uv, float str){
    vec2  c = uv - 0.5;
    return 1.0 - smoothstep(0.35, 0.85, length(c)) * str;
}

void main(){
    vec2 uv  = gl_FragCoord.xy / iResolution;
    vec3 col = texture(iChannel0, uv).rgb;

    // Bloom
    col += bloom(uv, iPostBloom + iBass * 0.15);

    // Tone mapping ACES
    col = aces(col);

    // Saturation
    float sat = iPostSat;
    float lum = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(vec3(lum), col, sat);

    // Contraste
    col = (col - 0.5) * iPostContrast + 0.5;

    // LUT
    if(iPostLUT > 0.5)
        col = applyLUT(col);

    // Aberration chromatique réactive audio
    float ca = iKick * 0.006;
    if(ca > 0.001){
        col.r = texture(iChannel0, uv + vec2( ca, 0.0)).r;
        col.b = texture(iChannel0, uv - vec2( ca, 0.0)).b;
    }

    // Vignette
    col *= vignette(uv, iPostVig + iEnergy * 0.3);

    // Grain
    col += grain(uv, iTime, iPostGrain);

    col = clamp(col, 0.0, 1.0);
    fragColor = vec4(col, 1.0);
}
