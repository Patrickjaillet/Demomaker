#version 330
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

mat2 rot(float a){ float c=cos(a),s=sin(a); return mat2(c,s,-s,c); }
float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }

// Simplex-like noise
float noise(vec2 p){
    vec2 i=floor(p), f=fract(p);
    f=f*f*(3.0-2.0*f);
    float a=hash(i), b=hash(i+vec2(1,0)), c=hash(i+vec2(0,1)), d=hash(i+vec2(1,1));
    return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);
}
float fbm(vec2 p){
    float s=0.0,a=0.5;
    for(int i=0;i<6;i++){ s+=a*noise(p); p=p*2.1+vec2(1.3,0.7); a*=0.5; }
    return s;
}

// Raymarching plasma cloud
float plasma(vec3 p){
    p.xy *= rot(iTime*0.12);
    p.xz *= rot(iTime*0.07);
    float d = length(p) - 1.2;
    d += fbm(p.xy*1.5 + iTime*0.3) * 0.8;
    d += fbm(p.yz*1.8 - iTime*0.2) * 0.5;
    d += fbm(p.xz*2.0 + iTime*0.15) * 0.3;
    return d * 0.4;
}

void main(){
    vec2 uv = (gl_FragCoord.xy - iResolution*0.5) / iResolution.y;

    // Ray setup
    vec3 ro = vec3(0.0, 0.0, -3.5 + iSceneProgress*0.5);
    vec3 rd = normalize(vec3(uv, 1.0));
    rd.xy *= rot(iTime * 0.05);
    rd.xz *= rot(iTime * 0.03);

    // Raymarching
    vec3  col = vec3(0.0);
    float t   = 0.0;
    float glow = 0.0;
    for(int i=0; i<64; i++){
        vec3 p = ro + rd * t;
        float d = plasma(p);
        if(d < 0.01){
            // Inside plasma — accumulate color
            float dens = 1.0 - smoothstep(0.0, 0.5, d);
            vec3 hue = 0.5 + 0.5*cos(6.28*(vec3(0.0,0.33,0.66) + length(p)*0.3 - iTime*0.2));
            col += hue * dens * 0.08 * (1.0 + iKick*1.5);
            glow += dens * 0.04;
        }
        t += max(d, 0.02);
        if(t > 8.0 || glow > 1.0) break;
    }

    // Feedback trail
    vec2 fuv = gl_FragCoord.xy / iResolution.xy;
    fuv += (uv - fbm(uv*3.0+iTime*0.1)*0.002);
    vec3 prev = texture(iChannel0, fuv).rgb * 0.92;

    fragColor = vec4(max(col, prev), 1.0);
}
