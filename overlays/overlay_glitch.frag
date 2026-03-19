#version 330
uniform sampler2D iChannel0;
uniform vec2  iResolution;
uniform float iTime;
uniform float iLocalTime;
uniform float iDuration;
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
uniform sampler2D iSpectrum;
uniform sampler2D iWaveform;
out vec4 fragColor;

float hash(vec2 p){ return fract(sin(dot(p,vec2(12.9898,78.233)))*43758.5453); }

void main(){
    vec2 uv = gl_FragCoord.xy / iResolution.xy;

    // Tremblement horizontal : amplitude sur kick + basses
    float shake = (iKick * 0.04 + iBass * 0.02);
    if(shake > 0.01)
        uv.x += (hash(vec2(floor(iTime*30.0), uv.y)) - 0.5) * shake;

    // Déchirures de blocs verticaux sur le beat
    float block = floor(uv.y * 20.0);
    if(iBeat > 0.8)
        uv.x += (hash(vec2(block, floor(iTime*8.0))) - 0.5) * iBeat * 0.08;

    // RGB split : amplitude proportionnelle aux aigus
    float shift = iHigh * 0.025 + iKick * 0.015;
    float r = texture(iChannel0, uv + vec2( shift, 0.0)).r;
    float g = texture(iChannel0, uv                   ).g;
    float b = texture(iChannel0, uv - vec2( shift, 0.0)).b;
    float a = texture(iChannel0, uv                   ).a;

    // Scanline colorée sur BPM
    float bpm_phase = mod(iLocalTime * iBPM / 60.0, 1.0);
    float scan_y = mod(uv.y + bpm_phase, 0.05);
    float scan = smoothstep(0.004, 0.0, abs(scan_y - 0.025)) * iMid * 0.3;
    r += scan * 0.5; g += scan * 0.2;

    // Clignotement
    float flicker = 0.92 + 0.08 * sin(iTime * 30.0 + iHigh * 10.0);

    float fade = smoothstep(0.0, 0.4, iLocalTime) * smoothstep(iDuration, iDuration-0.4, iLocalTime);

    fragColor = vec4(r, g, b, a * fade * flicker);
}
