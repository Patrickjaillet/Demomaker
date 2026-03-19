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
uniform sampler2D iChannel0;  // feedback
out vec4 fragColor;

// ── Utils ────────────────────────────────────────────────────────────────────
float hash(float n){ return fract(sin(n)*43758.5453); }
float hash2(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
mat2  rot(float a){ float c=cos(a),s=sin(a); return mat2(c,s,-s,c); }

float noise(vec2 p){
    vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
    return mix(mix(hash2(i),hash2(i+vec2(1,0)),f.x),
               mix(hash2(i+vec2(0,1)),hash2(i+vec2(1,1)),f.x),f.y);
}
float fbm(vec2 p, int oct){
    float s=0.0,a=0.5;
    for(int i=0;i<oct;i++){ s+=a*noise(p); p=p*2.01+vec2(5.2,1.3); a*=0.5; }
    return s;
}

// ── Aurora curtains ──────────────────────────────────────────────────────────
// Each curtain is a vertical ribbon of light moving slowly
float curtain(vec2 uv, float offset, float speed, float width){
    // Horizontal drift driven by fbm
    float drift = fbm(vec2(uv.y*0.8 + offset, iTime*speed*0.3), 4) * 2.0 - 1.0;
    float x     = uv.x - (offset * 0.35 + drift * 0.25);
    // Vertical fade: stronger near horizon, fades at top
    float yfade = smoothstep(-0.1, 0.3, uv.y) * smoothstep(1.2, 0.5, uv.y);
    // Ripple along the ribbon
    float ripple = sin(uv.y * 8.0 + iTime * speed * 2.0 + offset * 3.14159) * 0.04;
    x += ripple;
    float band = exp(-x*x / (width*width));
    return band * yfade;
}

// ── Stars ────────────────────────────────────────────────────────────────────
float stars(vec2 uv, float density){
    vec2 grid = floor(uv * density);
    vec2 local = fract(uv * density) - 0.5;
    float seed  = hash2(grid);
    float sz    = 0.005 + seed * 0.012;
    float twinkle = 0.6 + 0.4*sin(iTime*(1.0+seed*3.0) + seed*6.28);
    return smoothstep(sz, 0.0, length(local)) * twinkle * step(0.7, seed);
}

void main(){
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    // Remap: horizon at y=0.35, zenith at y=1
    vec2 sky = vec2(uv.x*2.0-1.0, (uv.y - 0.25) / 0.75);

    // ── Sky gradient ────────────────────────────────────────────────────────
    vec3 col = mix(
        vec3(0.01,0.015,0.04),    // dark ground
        vec3(0.0,0.01,0.025),     // deep space
        smoothstep(0.0,1.0,uv.y)
    );

    // ── Stars ───────────────────────────────────────────────────────────────
    float st  = stars(uv*vec2(1.8,1.2), 80.0)
              + stars(uv*vec2(1.3,0.9) + 0.17, 60.0)
              + stars(uv*vec2(2.1,1.5) + 0.33, 100.0);
    float stardim = smoothstep(0.3,0.5,uv.y); // hide stars near horizon
    col += vec3(0.9,0.95,1.0) * st * stardim * 0.8;

    // ── Moon ────────────────────────────────────────────────────────────────
    vec2 moonpos = vec2(0.78, 0.82);
    float moon   = smoothstep(0.035,0.025, length(uv - moonpos));
    col += vec3(0.95,0.95,0.85) * moon;
    // Moon halo
    col += vec3(0.3,0.3,0.2) * exp(-length(uv-moonpos)*18.0) * 0.15;

    // ── Aurora curtains ─────────────────────────────────────────────────────
    // Multiple overlapping curtains with different speeds and colours
    float speed = 0.4 + iSceneProgress * 0.3;

    struct { float off; float spd; float w; vec3 col; } curtains[6];
    // green primary (oxygen ~557nm)
    float c0 = curtain(sky, -0.6, speed*1.0,  0.25);
    float c1 = curtain(sky,  0.0, speed*0.7,  0.30);
    float c2 = curtain(sky,  0.5, speed*1.3,  0.20);
    // purple/red fringe (oxygen ~630nm, nitrogen)
    float c3 = curtain(sky, -0.3, speed*0.9,  0.15);
    float c4 = curtain(sky,  0.7, speed*1.1,  0.22);
    // teal variant
    float c5 = curtain(sky, -0.9, speed*0.6,  0.18);

    // Kick makes aurora pulse brighter
    float pulse = 1.0 + iKick * 2.5;

    vec3 aurora = vec3(0.0);
    aurora += vec3(0.05, 1.0, 0.3)  * c0 * 0.9 * pulse;
    aurora += vec3(0.1,  0.9, 0.4)  * c1 * 1.2 * pulse;
    aurora += vec3(0.0,  0.8, 0.5)  * c2 * 0.7 * pulse;
    aurora += vec3(0.6,  0.0, 1.0)  * c3 * 0.8 * pulse;  // purple fringe
    aurora += vec3(0.8,  0.1, 0.5)  * c4 * 0.5 * pulse;  // pink
    aurora += vec3(0.0,  0.7, 0.9)  * c5 * 1.0 * pulse;  // teal

    // Temporal shimmer: modulate by a slow noise field
    float shimmer = 0.7 + 0.3*fbm(sky*2.0 + iTime*0.15, 3);
    aurora *= shimmer;

    col += aurora;

    // ── Landscape silhouette ─────────────────────────────────────────────────
    // Treeline: mountains + fir trees
    float mx = uv.x * 6.28;
    float mountain = 0.18 + sin(mx*0.5)*0.04 + sin(mx*1.3)*0.03 + sin(mx*2.7)*0.015;
    float trees    = mountain + 0.025*max(0.0,sin(mx*12.0)) + 0.01*max(0.0,sin(mx*23.0));
    float land     = smoothstep(trees+0.005, trees-0.005, uv.y);
    col = mix(col, vec3(0.005,0.008,0.012), land);

    // ── Feedback glow ────────────────────────────────────────────────────────
    vec2 fuv = gl_FragCoord.xy / iResolution.xy;
    // Slight upward drift for the trail
    vec3 prev = texture(iChannel0, fuv + vec2(0.0, 0.0003)).rgb * 0.92;
    col = max(col, prev * 0.5);

    fragColor = vec4(col, 1.0);
}
