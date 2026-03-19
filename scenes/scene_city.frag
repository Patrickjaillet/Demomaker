#version 330
uniform sampler2D iChannel0; // A raw
uniform sampler2D iChannel1; // B
uniform sampler2D iChannel2; // C bloom
uniform sampler2D iChannel3; // D
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

vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }

void main(){
    vec2 uv  = gl_FragCoord.xy / iResolution.xy;
    vec2 c   = uv - 0.5;

    // Anamorphic lens flare on bright spots
    vec2 anam = vec2(c.x * 0.003 + iKick*0.002, 0.0);

    vec3 raw   = texture(iChannel0, uv).rgb;
    vec3 bloom = texture(iChannel2, uv).rgb;
    vec3 bloomR= texture(iChannel2, uv + anam*2.0).rgb;
    vec3 bloomB= texture(iChannel2, uv - anam*2.0).rgb;

    // Anamorphic: only horizontal smear
    vec3 anamBloom = vec3(bloomR.r, bloom.g, bloomB.b);

    vec3 col = raw + bloom * 1.2 + anamBloom * (0.8 + iKick*1.5);

    // Teal/orange grade (cyberpunk LUT approximation)
    col.r = pow(col.r, 0.9) * 1.05;
    col.g = pow(col.g, 1.0) * 0.95;
    col.b = pow(col.b, 0.85) * 1.10;

    col = aces(col);

    // Scanlines (very subtle)
    float scan = 0.97 + 0.03*sin(gl_FragCoord.y*3.14159);
    col *= scan;

    // Noise grain
    float grain = fract(sin(dot(uv+iTime*0.1,vec2(12.9898,78.233)))*43758.5453) * 0.04;
    col += grain - 0.02;

    // Fade in/out
    float fade = smoothstep(0.0,0.06,iSceneProgress)*smoothstep(1.0,0.94,iSceneProgress);
    col *= fade;

    // Vignette
    col *= 1.0 - smoothstep(0.3,0.85,length(c));

    fragColor = vec4(max(col,vec3(0.0)), 1.0);
}
