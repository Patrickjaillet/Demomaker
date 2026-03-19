#version 330
// @param float iTunnelSpeed  0.1  5.0  1.0
// @param float iTwist        0.0  3.0  0.5
// @param color iCoreColor    #bf5fff
// @param float iRingCount    2.0 20.0  8.0
// @param bool  iChromatic    true
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

    // Warp radial pilotée par les basses
    float warp = 0.015 + iBass * 0.035;
    vec2 wuv = 0.5 + c * (1.0 - warp * exp(-length(c)*3.0));

    vec3 raw   = texture(iChannel0, wuv).rgb;
    vec3 bloom = texture(iChannel2, wuv).rgb;

    // Aberration chromatique : éclatement sur les aigus
    float ca = length(c) * 0.015 + iHigh * 0.018;
    vec3 colR = texture(iChannel0, 0.5+c*(1.0+ca)).rgb;
    vec3 colB = texture(iChannel0, 0.5+c*(1.0-ca)).rgb;
    raw = vec3(colR.r, raw.g, colB.b);

    // Bloom sur les médiums
    vec3 col = raw + bloom * (1.5 + iMid * 3.0);

    // Glow central : pulse sur le kick, teinte sur BPM
    float bpm_phase = mod(iTime * iBPM / 60.0, 1.0);
    float core = exp(-length(c)*6.0) * (1.0 + iKick*4.0 + iBeat*2.0);
    // Couleur du glow oscille sur le BPM
    vec3 glow_col = mix(vec3(0.8,0.3,1.0), vec3(0.2,0.8,1.0), bpm_phase);
    col += glow_col * core;

    // Anneau de spectre autour du tunnel
    float r = length(c);
    float spec_r = clamp(r * 2.5, 0.0, 1.0);
    float spec_amp = texture(iSpectrum, vec2(spec_r, 0.5)).r;
    float ring = smoothstep(0.005, 0.0, abs(r - 0.18 - spec_amp * 0.15));
    col += vec3(0.0, 1.0, 0.6) * ring * (0.5 + iBass);

    // Flash blanc sur beat fort
    col += iBeat * 0.2;

    col = aces(col * 1.3);

    float fade = smoothstep(0.0,0.05,iSceneProgress)*smoothstep(1.0,0.95,iSceneProgress);
    col *= fade;

    col *= 1.0 - smoothstep(0.25, 0.75, length(c)*1.2);

    fragColor = vec4(col, 1.0);
}
