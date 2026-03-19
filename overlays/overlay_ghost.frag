#version 330
uniform sampler2D iChannel0;
uniform vec2 iResolution;
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
uniform float iLocalTime;
out vec4 fragColor;

void main() {
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    vec2 center = uv - 0.5;
    
    // Décalage des couches
    float zoom = 1.0 + (iKick * 0.1);
    vec4 colR = texture(iChannel0, center * (zoom + 0.02) + 0.5);
    vec4 colG = texture(iChannel0, center * zoom + 0.5);
    vec4 colB = texture(iChannel0, center * (zoom - 0.02) + 0.5);
    
    vec4 finalCol = vec4(colR.r, colG.g, colB.b, colG.a);
    float fade = smoothstep(0.0, 0.5, iLocalTime) * smoothstep(iDuration, iDuration - 0.5, iLocalTime);
    
    fragColor = finalCol * fade * 1.2;
}