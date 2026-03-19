#version 330
// @param float iSpeed     0.1  4.0   1.0
// @param float iDensity   0.5  3.0   1.0
// @param color iColorA    #ff4500
// @param color iColorB    #00f5ff
// @param float iGlowMix   0.0  2.0   1.0
uniform sampler2D iChannel0; // A raw plasma
uniform sampler2D iChannel1; // B (unused)
uniform sampler2D iChannel2; // C bloom
uniform sampler2D iChannel3; // D (unused)
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

    // Lens distortion pilotée par les basses
    float r2 = dot(c,c);
    uv = 0.5 + c * (1.0 + r2 * 0.12 * (1.0 + iBass*0.5));

    vec3 raw   = texture(iChannel0, uv).rgb;
    vec3 bloom = texture(iChannel2, uv).rgb;

    // Bloom modulé par les médiums
    vec3 col = raw + bloom * (1.8 + iMid * 2.5);

    // Aberration chromatique : amplitude sur les aigus, éclair sur kick
    float ca = 0.002 + iHigh * 0.008 + iKick * 0.006;
    col.r = mix(col.r, texture(iChannel2, uv + vec2( ca, 0.0)).r, 0.6);
    col.b = mix(col.b, texture(iChannel2, uv - vec2( ca, 0.0)).b, 0.6);

    // Teinte qui dérive sur le BPM
    float bpm_phase = mod(iTime * iBPM / 60.0, 1.0);
    float hue_shift = bpm_phase * 0.15;
    col = mix(col, col.gbr, hue_shift * iBeat * 0.3);

    // Flash de beat (éclair blanc bref)
    col += iBeat * 0.15;

    // Waveform incrustée horizontalement au centre
    float wy = abs(uv.y - 0.5) - 0.01;
    float wave = texture(iWaveform, vec2(uv.x, 0.5)).r * 2.0 - 1.0;
    float wave_y = wave * 0.06 * (1.0 + iBass);
    float wline = smoothstep(0.004, 0.0, abs((uv.y - 0.5) - wave_y));
    col = mix(col, vec3(0.0, 1.0, 0.8), wline * 0.5);

    col = aces(col * 1.4);

    // Fade de scène
    float fade = smoothstep(0.0, 0.05, iSceneProgress) * smoothstep(1.0, 0.95, iSceneProgress);
    col *= fade;

    // Vignette
    float vig = 1.0 - smoothstep(0.35, 0.85, length(c));
    col *= vig;

    fragColor = vec4(col, 1.0);
}
