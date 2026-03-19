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
    vec2 c  = uv - 0.5;

    // Vignette dynamique : se resserre sur le kick, s'ouvre sur les basses
    float vig_radius = 0.55 - iKick * 0.1 + iBass * 0.05;
    float vig = 1.0 - smoothstep(vig_radius, vig_radius + 0.35, length(c));

    // Glitch de bord : distorsion sur les aigus
    float edge = smoothstep(0.3, 0.5, length(c));
    if(edge > 0.0 && iHigh > 0.3){
        uv.x += (hash(vec2(floor(iTime*15.0), floor(uv.y*40.0))) - 0.5) * edge * iHigh * 0.04;
    }

    // RGB split radial sur kick
    float ca = iKick * 0.012 * edge;
    float r = texture(iChannel0, uv + c*ca).r;
    float g = texture(iChannel0, uv       ).g;
    float b = texture(iChannel0, uv - c*ca).b;
    float a = texture(iChannel0, uv       ).a;
    vec3 col = vec3(r,g,b) * vig;

    // Halo BPM : anneau pulsant
    float bpm_phase = mod(iLocalTime * iBPM / 60.0, 1.0);
    float ring = smoothstep(0.006, 0.0, abs(length(c) - 0.4 - bpm_phase * 0.12)) * iBeat * 0.6;
    col += vec3(0.0, 0.8, 1.0) * ring;

    float fade = smoothstep(0.0,0.3,iLocalTime)*smoothstep(iDuration,iDuration-0.3,iLocalTime);
    fragColor = vec4(col * fade, a * vig * fade);
}
