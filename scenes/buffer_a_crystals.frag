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
uniform sampler2D iChannel0;
out vec4 fragColor;

mat2 rot(float a){ float c=cos(a),s=sin(a); return mat2(c,s,-s,c); }

// IFS crystal: fold+scale
vec3 fold(vec3 p){
    // Menger-like folds
    p = abs(p);
    if(p.x<p.y) p.xy=p.yx;
    if(p.x<p.z) p.xz=p.zx;
    if(p.y<p.z) p.yz=p.zy;
    return p;
}

float DE(vec3 p){
    vec3 q = p;
    float scale = 2.0;
    float d = 1e9;
    for(int i=0; i<8; i++){
        q = fold(q);
        q = q * scale - vec3(scale-1.0);
        // Pulse with kick
        float ks = scale + iKick * 0.3 * sin(float(i)*1.3+iTime);
        d = min(d, (length(q) - 0.5) / pow(ks, float(i)));
    }
    return d * 0.3;
}

vec3 normal(vec3 p){
    vec2 e=vec2(0.001,0.0);
    return normalize(vec3(DE(p+e.xyy)-DE(p-e.xyy), DE(p+e.yxy)-DE(p-e.yxy), DE(p+e.yyx)-DE(p-e.yyx)));
}

void main(){
    vec2 uv = (gl_FragCoord.xy - iResolution*0.5) / iResolution.y;

    // Orbiting camera
    float angle = iTime * 0.15 + iSceneProgress * 0.8;
    vec3 ro = vec3(cos(angle)*2.8, sin(iTime*0.1)*0.4, sin(angle)*2.8);
    vec3 target = vec3(0.0);
    vec3 fwd = normalize(target - ro);
    vec3 rgt = normalize(cross(fwd, vec3(0,1,0)));
    vec3 up  = cross(rgt, fwd);
    vec3 rd  = normalize(fwd + uv.x*rgt + uv.y*up);

    // March
    float t = 0.0;
    vec3 col = vec3(0.0);
    bool hit = false;
    for(int i=0; i<120; i++){
        vec3 p = ro + rd * t;
        float d = DE(p);
        if(d < 0.003){
            // Shading
            vec3 n = normal(p);
            vec3 ld = normalize(vec3(1.0,1.5,-1.0));
            float diff = max(dot(n,ld), 0.0);
            float spec = pow(max(dot(reflect(-ld,n),-rd),0.0), 32.0);

            // Crystal color: iridescent
            vec3 refl = reflect(rd, n);
            float fres = pow(1.0-abs(dot(n,-rd)), 3.0);
            vec3 base  = 0.5+0.5*cos(6.28*(vec3(0.0,0.33,0.66)+length(p)*0.5-iTime*0.1));
            col = base * (diff*0.8 + 0.2);
            col += vec3(1.0) * spec * (0.5 + fres);
            col += base * fres * (1.0 + iKick*1.5);
            col *= 1.5 + iKick;
            hit = true; break;
        }
        t += max(d, 0.005);
        if(t > 12.0) break;
    }

    if(!hit){
        // Dark cave background with subtle glow
        col = vec3(0.01,0.0,0.03) * (1.0 + exp(-length(uv)*2.0)*iKick);
    }

    // AO glow: step count based darkening
    float ao = 1.0 - float(hit ? 0 : 1) * 0.0; // placeholder — built into march above

    fragColor = vec4(col, 1.0);
}
