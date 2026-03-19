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

float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
float hash1(float x){ return fract(sin(x*374.23)*43758.5); }

void main(){
    vec2 uv  = gl_FragCoord.xy / iResolution.xy;
    vec2 uvn = uv;

    // Blocs de disruption : intensité sur iBeat + iBass
    float disrupt = iBeat * 0.8 + iBass * 0.3;
    float row  = floor(uvn.y * 30.0);
    float tslot = floor(iTime * 12.0);
    if(hash(vec2(row, tslot)) < disrupt * 0.6)
        uvn.x = fract(uvn.x + (hash(vec2(row, tslot+1.0)) - 0.5) * 0.3 * disrupt);

    // Décalage vertical de lignes sur kick
    if(iKick > 0.6){
        float krow = floor(uvn.y * 60.0);
        uvn.y = fract(uvn.y + hash1(krow + floor(iTime*20.0)) * 0.02 * iKick);
    }

    // Échantillonnage RGB splitté : largeur sur iHigh
    float ca = iHigh * 0.012 + iKick * 0.008;
    float r = texture(iChannel0, uvn + vec2( ca, 0.0)).r;
    float g = texture(iChannel0, uvn              ).g;
    float b = texture(iChannel0, uvn - vec2( ca, 0.0)).b;
    float a = texture(iChannel0, uvn              ).a;
    vec3 col = vec3(r, g, b);

    // Teinte numérique (cyan/magenta) modulée par spectre
    float spec_mid = texture(iSpectrum, vec2(0.4, 0.5)).r;
    vec3 digital = mix(vec3(0.0,1.0,0.9), vec3(1.0,0.0,0.8), spec_mid);
    col = mix(col, col * digital * 1.3, iMid * 0.25);

    // Flash sur beat fort
    col += iBeat * 0.15;

    // Pixel noise sur les aigus
    float noise = hash(uvn * iResolution * 0.5 + iTime) * iHigh * 0.12;
    col = mix(col, vec3(noise), iHigh * 0.1);

    float fade = smoothstep(0.0, 0.3, iLocalTime) * smoothstep(iDuration, iDuration-0.3, iLocalTime);

    fragColor = vec4(col * fade, a * fade);
}
