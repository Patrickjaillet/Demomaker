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
    
    // Calcul du zoom : de 0.0 à 1.0 avec un effet d'élan (expo)
    float progress = clamp(iLocalTime / 1.5, 0.0, 1.0); // Animation sur les 1.5 premières secondes
    float zoom = pow(progress, 3.0); 
    
    // On ajoute une petite pulsation sur le Kick
    zoom += iKick * 0.05;
    
    // Application du zoom (on divise les coordonnées par le facteur de zoom)
    vec2 zoomedUV = center / max(zoom, 0.001) + 0.5;
    
    vec4 col = vec4(0.0);
    if(zoomedUV.x >= 0.0 && zoomedUV.x <= 1.0 && zoomedUV.y >= 0.0 && zoomedUV.y <= 1.0) {
        col = texture(iChannel0, zoomedUV);
    }
    
    float fade = smoothstep(0.0, 0.2, iLocalTime) * smoothstep(iDuration, iDuration - 0.5, iLocalTime);
    fragColor = col * fade;
}