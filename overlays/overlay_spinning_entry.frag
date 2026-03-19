#version 330
uniform sampler2D iChannel0;
uniform vec2 iResolution;
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
uniform sampler2D iSpectrum;  // unit 8 — spectre log [0,1]
uniform sampler2D iWaveform;  // unit 9 — waveform  [0,1]
out vec4 fragColor;

mat2 rot(float a) { float c=cos(a), s=sin(a); return mat2(c,s,-s,c); }

void main() {
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    vec2 center = uv - 0.5;
    
    // La rotation ralentit progressivement
    float angle = exp(-iLocalTime) * 10.0 + iLocalTime * 0.5;
    angle += iKick * 0.2; // La rotation réagit au kick
    
    vec2 rotatedUV = rot(angle) * center + 0.5;
    
    vec4 col = vec4(0.0);
    if(rotatedUV.x >= 0.0 && rotatedUV.x <= 1.0 && rotatedUV.y >= 0.0 && rotatedUV.y <= 1.0) {
        col = texture(iChannel0, rotatedUV);
    }
    
    float fade = smoothstep(0.0, 0.5, iLocalTime) * smoothstep(iDuration, iDuration - 0.5, iLocalTime);
    fragColor = col * fade;
}