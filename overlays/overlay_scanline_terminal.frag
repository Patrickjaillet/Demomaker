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

void main(){
    vec2 uv = gl_FragCoord.xy / iResolution.xy;

    // Scanlines : densité modulée par les médiums
    float lines = 200.0 + iMid * 100.0;
    float scan = 0.85 + 0.15 * sin(uv.y * lines * 3.14159);

    // Phosphore vert classique, teinte sur BPM
    float bpm_phase = mod(iLocalTime * iBPM / 60.0, 1.0);
    vec3 phosphor = mix(vec3(0.1, 1.0, 0.2), vec3(0.1, 0.6, 1.0), bpm_phase * iBeat * 0.5);

    vec4 tex = texture(iChannel0, uv);
    float lum = dot(tex.rgb, vec3(0.299, 0.587, 0.114));

    // Waveform incrustée en vert CRT
    float wave = texture(iWaveform, vec2(uv.x, 0.5)).r * 2.0 - 1.0;
    float wline = smoothstep(0.004, 0.0, abs((uv.y - 0.5) - wave * 0.1 * (1.0 + iBass)));
    vec3 col = mix(lum * phosphor * scan, phosphor, wline * 0.8);

    // Bruit CRT sur les aigus
    float crt_noise = fract(sin(dot(uv * iResolution + iTime * 100.0, vec2(12.9, 78.2))) * 43758.5);
    col += (crt_noise - 0.5) * 0.04 * iHigh;

    // Bloom de kick
    col *= 1.0 + iKick * 0.3;

    float fade = smoothstep(0.0,0.4,iLocalTime)*smoothstep(iDuration,iDuration-0.4,iLocalTime);
    fragColor = vec4(col * fade, tex.a * fade);
}
