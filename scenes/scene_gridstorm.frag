#version 330
// @param float iGridScale   1.0 20.0  6.0
// @param float iSpeed       0.1  5.0  1.0
// @param color iLineColor   #00f5ff
// @param float iPerspective 0.1  2.0  0.8
// @param bool  iReflect     false
uniform sampler2D iChannel0; // A
uniform sampler2D iChannel1; // B
uniform sampler2D iChannel2; // C
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

vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }\

void main(){
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    vec2 c  = uv - 0.5;

    // Zoom et rotation sur le kick
    float zoom = 1.0 + iKick * 0.04;
    float angle = iBass * 0.05 * sin(iTime * 0.5);
    mat2 rot = mat2(cos(angle), -sin(angle), sin(angle), cos(angle));
    vec2 wuv = 0.5 + rot * (c / zoom);

    vec3 raw   = texture(iChannel0, wuv).rgb;
    vec3 bloom = texture(iChannel2, wuv).rgb;

    vec3 col = raw + bloom * (1.0 + iMid * 2.0);

    // Couleur de grille modulée par spectre horizontal
    float spec = texture(iSpectrum, vec2(uv.x, 0.5)).r;
    vec3 grid_col = mix(vec3(0.0,0.5,1.0), vec3(1.0,0.2,0.0), spec);
    col = mix(col, col * grid_col * 1.5, 0.3 + iMid * 0.3);

    // Scanlines BPM : lignes horizontales qui pulsent sur le beat
    float bpm_phase = mod(iTime * iBPM / 60.0, 1.0);
    float scan_y = mod(uv.y - bpm_phase * 0.5, 0.1);
    float scan = smoothstep(0.005, 0.0, abs(scan_y - 0.05)) * iBeat * 0.5;
    col += vec3(0.0, 1.0, 0.5) * scan;

    // Waveform en overlay central
    float wave = texture(iWaveform, vec2(uv.x, 0.5)).r * 2.0 - 1.0;
    float wline = smoothstep(0.003, 0.0, abs((uv.y - 0.5) - wave * 0.08 * (1.0 + iBass)));
    col = mix(col, vec3(1.0, 0.5, 0.0), wline * 0.7);

    // Flash kick
    col += iKick * 0.1;

    col = aces(col * 1.2);

    float fade = smoothstep(0.0,0.04,iSceneProgress)*smoothstep(1.0,0.96,iSceneProgress);
    col *= fade;

    float vig = 1.0 - smoothstep(0.35, 0.8, length(c));
    col *= vig;

    fragColor = vec4(col, 1.0);
}
