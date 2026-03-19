#version 330
uniform float iTime;
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
uniform sampler2D iSpectrum;  // unit 8 — spectre log [0,1]
uniform sampler2D iWaveform;  // unit 9 — waveform  [0,1]
uniform float iSceneProgress;
uniform sampler2D iChannel0;
uniform sampler2D iChannel1;
out vec4 fragColor;

void main(){
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    vec2 px = 1.0 / iResolution.xy;

    float r = 6.0 + iKick * 4.0;
    vec3 col = vec3(0.0);
    float wsum = 0.0;
    for(int i = -16; i <= 16; i++){
        float w = exp(-float(i*i) / (2.0*r*r));
        col  += texture(iChannel1, uv + vec2(0.0, float(i)*px.y*2.5)).rgb * w;
        wsum += w;
    }
    fragColor = vec4(col / wsum, 1.0);
}
