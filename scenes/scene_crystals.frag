#version 330
// @param float iZoom       0.5  4.0  1.5
// @param float iRotSpeed   0.0  2.0  0.3
// @param color iColor1     #00f5ff
// @param color iColor2     #ffcb47
// @param int   iFaces      3   12    6
uniform sampler2D iChannel0; // A
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
uniform sampler2D iSpectrum;  // unit 8
uniform sampler2D iWaveform;  // unit 9
uniform float iSceneProgress;
uniform float iTime;
out vec4 fragColor;

vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }

void main(){
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    vec2 c  = uv - 0.5;

    // Déformation cristalline pilotée par les bandes
    float r2 = dot(c,c);
    float bass_dist  = iBass * 0.04;
    float high_twist = iHigh * 0.08 * sin(iTime * 3.0);
    uv += c * (bass_dist * r2);
    uv.x += high_twist * c.y;
    uv.y -= high_twist * c.x;

    vec3 raw   = texture(iChannel0, uv).rgb;
    vec3 bloom = texture(iChannel2, uv).rgb;

    // Bloom irisé : canal R sur mid, B sur high
    vec3 col = raw;
    col.r += texture(iChannel2, uv + vec2(0.003 + iMid*0.006, 0.0)).r * (1.0 + iMid * 2.0);
    col.g += bloom.g * (1.0 + iMid * 1.5);
    col.b += texture(iChannel2, uv - vec2(0.003 + iHigh*0.006, 0.0)).b * (1.0 + iHigh * 2.5);

    // Pulse de spectre comme facettes lumineuses
    float spec_lo = texture(iSpectrum, vec2(0.1, 0.5)).r;  // sub
    float spec_hi = texture(iSpectrum, vec2(0.7, 0.5)).r;  // treble
    col += vec3(1.0, 0.4, 0.1) * spec_lo * 0.4;
    col += vec3(0.3, 0.5, 1.0) * spec_hi * 0.3;

    // Éclat de beat : flash blanc radial
    float beat_flash = iBeat * exp(-r2 * 8.0);
    col += beat_flash * 0.5;

    // BPM hue cycle
    float bpm_t = mod(iTime * iBPM / 60.0, 3.0);
    vec3 hue_cycle = 0.5 + 0.5 * cos(6.28 * (vec3(0.0,0.33,0.66) + bpm_t * 0.33));
    col = mix(col, col * hue_cycle * 1.3, 0.15 + iMid * 0.15);

    col = aces(col * 1.5);

    float fade = smoothstep(0.0,0.04,iSceneProgress)*smoothstep(1.0,0.96,iSceneProgress);
    col *= fade;

    float vig = 1.0 - smoothstep(0.3, 0.8, length(c));
    col *= vig;

    fragColor = vec4(col, 1.0);
}
