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

void main() {
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    vec2 center = uv - 0.5;
    
    // Simulation de perspective
    float angle = cos(iLocalTime * 2.0) * exp(-iLocalTime * 0.5);
    float perspective = 1.0 + center.x * sin(angle);
    
    vec2 flipUV = center;
    flipUV.x /= max(cos(angle), 0.01); // Compression horizontale
    flipUV += 0.5;
    
    vec4 col = vec4(0.0);
    if(flipUV.x >= 0.0 && flipUV.x <= 1.0 && flipUV.y >= 0.0 && flipUV.y <= 1.0) {
        col = texture(iChannel0, flipUV);
    }
    
    // Le kick fait "vibrer" la perspective
    col.rgb += iKick * 0.1;
    
    float fade = smoothstep(0.0, 0.3, iLocalTime) * smoothstep(iDuration, iDuration - 0.3, iLocalTime);
    fragColor = col * fade;
}