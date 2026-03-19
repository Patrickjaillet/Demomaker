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
float hash(float n){ return fract(sin(n)*43758.5453); }
float hash2(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }

// Tunnel warp
vec2 tunnelUV(vec2 uv, float t){
    float r   = length(uv);
    float a   = atan(uv.y, uv.x);
    float z   = 0.5 / r;              // depth = inverse radius
    float tu  = a / (2.0*3.14159) + 0.5;
    float tv  = z + t;
    return vec2(tu, tv);
}

float noise(vec2 p){
    vec2 i=floor(p), f=fract(p);
    f=f*f*(3.0-2.0*f);
    float a=hash2(i),b=hash2(i+vec2(1,0)),c=hash2(i+vec2(0,1)),d=hash2(i+vec2(1,1));
    return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);
}

void main(){
    vec2 uv = (gl_FragCoord.xy - iResolution*0.5) / iResolution.y;

    // Twist
    float twist = iTime * 0.3 + iSceneProgress * 1.5;
    uv *= rot(twist * 0.2 + length(uv)*1.5);

    // Speed surge on kick
    float speed = 1.2 + iKick * 3.0 + iSceneProgress * 0.5;
    vec2 tuv = tunnelUV(uv, iTime * speed);

    // Layer 1: primary tunnel walls
    float layers = 0.0;
    for(int i=0; i<8; i++){
        float fi = float(i);
        vec2 luv = tuv * pow(2.0, fi) + vec2(fi*0.13, 0.0);
        layers += noise(luv) / pow(2.0, fi);
    }

    // Layer 2: neon rings
    float r     = length(uv);
    float rings = 0.5 + 0.5*sin((1.0/r - iTime*speed*0.5) * 12.0 + twist);
    rings       = pow(rings, 3.0);

    // Radial glow from center
    float glow  = exp(-r * 4.0) * (1.0 + iKick*2.0);

    // Color
    float hue_t = iTime * 0.1 + layers;
    vec3 col_a  = 0.5+0.5*cos(6.28*(vec3(0.0,0.33,0.66) + hue_t));
    vec3 col_b  = 0.5+0.5*cos(6.28*(vec3(0.0,0.33,0.66) + hue_t + 0.5));

    vec3 col = mix(col_a, col_b, layers) * rings * (2.0 + iKick);
    col += vec3(0.6,0.3,1.0) * glow;
    col += vec3(1.0,0.8,0.2) * rings * glow * iKick;

    // Feedback
    vec2 fuv = gl_FragCoord.xy / iResolution.xy;
    vec3 prev = texture(iChannel0, fuv).rgb * 0.88;
    col = max(col, prev);

    fragColor = vec4(col, 1.0);
}
