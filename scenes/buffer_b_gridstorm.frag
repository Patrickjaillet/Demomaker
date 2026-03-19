#version 330
// GRID STORM — Buffer B : Éclairs électriques déclenchés par le kick
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
uniform sampler2D iChannel0; // Buffer A (geometry)
out vec4 fragColor;

#define TAU 6.28318530718

float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
float hash1(float x){ return fract(sin(x*74.31)*15467.12); }

// Lightning bolt SDF le long d'un segment fractal
float lightning(vec2 p, vec2 a, vec2 b, float seed, int depth){
    float d = 1e6;
    vec2 ab = b - a;
    float len = length(ab);
    if(len < 0.005 || depth <= 0) {
        // Segment terminal
        vec2 h = clamp(dot(p-a, ab) / dot(ab,ab), 0.0, 1.0) * ab + a;
        return length(p - h);
    }
    // Milieu avec déviation
    float t = 0.5 + (hash1(seed) - 0.5) * 0.6;
    vec2 mid = mix(a, b, t);
    // Déviation perpendiculaire
    vec2 perp = normalize(vec2(-ab.y, ab.x));
    mid += perp * (hash1(seed + 1.3) - 0.5) * len * 0.4 * (1.0 + iKick * 0.5);

    // Récursion sur les deux moitiés
    float d1 = lightning(p, a,   mid, seed*1.7+0.3, depth-1);
    float d2 = lightning(p, mid, b,   seed*2.1+0.7, depth-1);
    return min(d1, d2);
}

void main(){
    vec2 uv = (gl_FragCoord.xy - iResolution*0.5) / iResolution.y;
    vec2 st = gl_FragCoord.xy / iResolution.xy;

    vec3 col = vec3(0.0);

    // Génère 4 éclairs ancrés sur le beat
    float beatPhase = mod(iTime * 2.5, 1.0);
    float beatStr   = pow(max(0.0, 1.0 - beatPhase * 2.0), 2.0) + iKick;

    for(int i = 0; i < 4; i++){
        float fi = float(i);
        // Origine aléatoire (se régénère chaque beat)
        float beatId = floor(iTime * 2.5) + fi * 100.0;
        vec2 origin = vec2(hash1(beatId + 1.0) - 0.5, hash1(beatId + 2.0) - 0.5) * 0.8;
        vec2 target = vec2(hash1(beatId + 3.0) - 0.5, hash1(beatId + 4.0) - 0.5) * 0.8;

        float bolt = lightning(uv, origin, target, beatId * 0.01 + fi, 6);

        float w  = 0.002 + iKick * 0.004;
        float glow = exp(-bolt * 60.0) * beatStr;
        float core = exp(-bolt * 600.0 / w);

        vec3 lc = mix(
            vec3(0.3, 0.7, 1.0),
            vec3(1.0, 0.5, 0.0),
            hash1(fi * 31.7)
        );

        col += lc * glow * (0.4 + iKick * 0.8);
        col += vec3(1.0, 0.95, 0.8) * core * beatStr * 2.0;
    }

    // Particules étincelles sur kick
    for(int i = 0; i < 12; i++){
        float fi = float(i);
        float beatId2 = floor(iTime * 4.0) + fi * 53.0;
        vec2 pos = vec2(hash1(beatId2) - 0.5, hash1(beatId2 + 1.0) - 0.5);
        float age  = fract(iTime * 4.0) * (0.5 + hash1(fi) * 0.5);
        vec2 vel   = normalize(vec2(hash1(fi+2.0)-0.5, hash1(fi+3.0)-0.5));
        pos += vel * age * 0.3;
        float d = length(uv - pos);
        float sz = mix(0.008, 0.001, age);
        col += vec3(0.5, 0.9, 1.0) * exp(-d / sz) * (1.0-age) * iKick * 1.5;
    }

    fragColor = vec4(col, 1.0);
}
