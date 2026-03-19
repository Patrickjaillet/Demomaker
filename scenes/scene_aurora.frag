#version 330
// @param float iWaveSpeed   0.1  3.0  0.8
// @param float iHeight      0.1  1.0  0.4
// @param color iColorLow    #00ff88
// @param color iColorHigh   #bf5fff
// @param float iRipple      0.0  2.0  0.5
uniform sampler2D iChannel0; // A aurora raw
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

    // Distortion verticale sur les basses (ondulation aurora)
    uv.y += iBass * 0.02 * sin(uv.x * 12.0 + iTime * 2.0);
    uv.x += iMid  * 0.01 * cos(uv.y * 8.0  + iTime * 1.5);

    vec3 raw   = texture(iChannel0, uv).rgb;
    vec3 bloom = texture(iChannel2, uv).rgb;

    vec3 col = raw + bloom * (1.2 + iMid * 1.8);

    // Coloration dynamique : teinte verte sur basses, violette sur aigus
    vec3 bass_tint = vec3(0.1, 0.9, 0.4) * iBass * 0.4;
    vec3 high_tint = vec3(0.7, 0.2, 1.0) * iHigh * 0.4;
    col += bass_tint + high_tint;

    // Spectre en bas comme horizon lumineux
    float horizon = smoothstep(0.12, 0.0, uv.y);
    float spec = texture(iSpectrum, vec2(uv.x, 0.5)).r;
    col += vec3(0.2, 1.0, 0.5) * horizon * spec * (0.5 + iBass * 1.5);

    // Flash de beat
    col += vec3(0.8, 0.9, 1.0) * iBeat * 0.12;

    // Aberration chromatique légère sur les aigus
    float ca = iHigh * 0.005;
    col.r += texture(iChannel0, uv + vec2(ca, 0.0)).r * 0.3;
    col.b += texture(iChannel0, uv - vec2(ca, 0.0)).b * 0.3;

    col = aces(col * 1.2);

    float fade = smoothstep(0.0,0.04,iSceneProgress)*smoothstep(1.0,0.96,iSceneProgress);
    col *= fade;

    float vig = 1.0 - smoothstep(0.4, 0.9, length(c));
    col *= vig;

    fragColor = vec4(col, 1.0);
}
