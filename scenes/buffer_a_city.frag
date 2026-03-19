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

float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
float hash1(float n){ return fract(sin(n)*43758.5453); }

// Building SDF
float sdBox(vec3 p, vec3 b){ vec3 q=abs(p)-b; return length(max(q,0.0))+min(max(q.x,max(q.y,q.z)),0.0); }

struct Hit { float d; float id; vec3 col; };

Hit map(vec3 p){
    Hit h; h.d=1e9; h.id=0.0; h.col=vec3(0.0);

    // Ground plane
    float ground = p.y + 0.0;
    if(ground < h.d){ h.d=ground; h.id=1.0; h.col=vec3(0.05,0.05,0.08); }

    // City grid of buildings
    vec2 grid = floor(p.xz / 4.0);
    vec2 local = mod(p.xz, 4.0) - 2.0;
    float seed = hash(grid);
    if(seed > 0.15){ // sparse empty lots
        float bw   = 0.7 + seed * 0.8;
        float bh   = 1.0 + seed * seed * 14.0;
        // Kick makes buildings pulse
        bh *= 1.0 + iKick * 0.08 * hash1(seed*7.3);
        vec3 bp    = vec3(local.x, p.y - bh, local.y);
        float bd   = sdBox(bp, vec3(bw, bh, bw));
        if(bd < h.d){
            h.d   = bd;
            h.id  = 2.0;
            // Building color palette: dark concrete + neon accent
            vec3 base = mix(vec3(0.06,0.07,0.1), vec3(0.12,0.1,0.15), seed);
            h.col = base;
        }
        // Rooftop neon light
        float top  = abs(p.y - bh*2.0) - 0.05;
        float side = sdBox(vec3(local.x, p.y-bh*2.0, local.y), vec3(bw+0.02,0.04,bw+0.02));
        float neon = side;
        if(neon < h.d){
            h.d = neon; h.id = 3.0;
            vec3 nc = 0.5+0.5*cos(6.28*vec3(0.0,0.33,0.66)*hash1(seed*3.1) + iTime*0.5);
            h.col = nc * (2.0 + iKick*3.0);
        }
    }
    return h;
}

vec3 normal(vec3 p){
    vec2 e=vec2(0.001,0.0);
    return normalize(vec3(
        map(p+e.xyy).d - map(p-e.xyy).d,
        map(p+e.yxy).d - map(p-e.yxy).d,
        map(p+e.yyx).d - map(p-e.yyx).d));
}

void main(){
    vec2 uv = (gl_FragCoord.xy - iResolution*0.5) / iResolution.y;

    // Camera: flying through city
    float speed = 3.0 + iSceneProgress * 2.0;
    vec3 ro = vec3(sin(iTime*0.07)*6.0, 2.5 + sin(iTime*0.13)*0.5, iTime * speed);
    vec3 target = ro + vec3(sin(iTime*0.05)*0.3, -0.15, 1.0);
    vec3 fwd = normalize(target - ro);
    vec3 rgt = normalize(cross(fwd, vec3(0,1,0)));
    vec3 up  = cross(rgt, fwd);
    vec3 rd  = normalize(fwd + uv.x*rgt + uv.y*up);

    // March
    float t = 0.0;
    Hit  hit; hit.d=1e9; hit.id=0.0;
    vec3 hitcol = vec3(0.0);
    bool found = false;
    for(int i=0; i<80; i++){
        vec3 p = ro + rd * t;
        Hit h = map(p);
        if(h.d < 0.005){
            hit=h; hitcol=h.col; found=true; break;
        }
        t += max(h.d * 0.7, 0.01);
        if(t > 80.0) break;
    }

    vec3 col = vec3(0.0);
    // Fog / sky gradient
    vec3 sky = mix(vec3(0.01,0.01,0.04), vec3(0.12,0.0,0.18), pow(max(0.0,rd.y+0.1),0.4));
    sky += vec3(0.0,0.05,0.2) * pow(max(0.0,-rd.y+0.3),2.0); // ground glow

    if(found){
        vec3 p = ro + rd * t;
        vec3 n = normal(p);

        if(hit.id == 1.0){ // ground
            // Wet ground reflections
            vec3 refl = reflect(rd, n);
            col = hitcol * 0.3;
            // Puddle neon reflections
            float puddle = smoothstep(0.3, 0.0, hash(floor(p.xz*1.5)));
            col += vec3(0.5,0.0,1.0)*puddle*0.3*(1.0+iKick) * max(0.0,refl.y);
            col += vec3(0.0,0.5,1.0)*puddle*0.2 * smoothstep(3.0,0.0,length(mod(p.xz,4.0)-2.0));
        } else if(hit.id == 2.0){ // building
            // Ambient + windows
            col = hitcol;
            float win = step(0.6, hash(floor(p*3.0).xz + floor(p.y*2.0)));
            col += vec3(0.8,0.6,0.3) * win * 0.15 * (0.5+0.5*sin(iTime+hash(floor(p*3.0).xz)*6.28));
            col += sky * 0.05;
        } else { // neon
            col = hitcol;
        }

        // Fog
        float fog = 1.0 - exp(-t * 0.012);
        col = mix(col, sky, fog);
    } else {
        col = sky;
    }

    // Rain streaks
    vec2 rain_uv = uv * vec2(50.0, 300.0) + vec2(iTime*5.0, iTime*80.0);
    float rain = step(0.97, hash(floor(rain_uv))) * smoothstep(0.5,0.0,fract(rain_uv.y));
    col += vec3(0.3,0.5,0.8) * rain * 0.3;

    fragColor = vec4(col, 1.0);
}
