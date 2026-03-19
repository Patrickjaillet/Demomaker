#version 330

uniform sampler2D iChannel0;
uniform float iTime;
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
uniform sampler2D iWaveform;  // unit 9 — waveform  [0,1] // Reçu du système
uniform vec2 iResolution;

out vec4 fragColor;

// Fonction de bruit pour le grain et le tremblement
float noise(vec2 p) {
    return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
    vec2 uv = gl_FragCoord.xy / iResolution.xy;

    // 1. EFFET DE SECOUSSE (SHAKE) - QUASI INVISIBLE
    // Réduit à 0.005 pour un frémissement très léger
    float shakeAmount = iKick * 0.005;
    vec2 shake = vec2(
        noise(vec2(iTime, 0.0)) - 0.5,
        noise(vec2(0.0, iTime)) - 0.5
    ) * shakeAmount;
    vec2 centeredUV = uv - 0.5 + shake;
    
    // 2. DISTORSION DE LENTILLE TRÈS DISCRÈTE
    // Le pulse est réduit à 0.02 pour éviter tout mouvement brusque
    float pulse = iKick * 0.02;
    float zoom = 1.0 + sin(iTime * 0.3) * 0.01 - pulse;
    vec2 distortedUV = centeredUV * zoom + 0.5;

    // 3. ABERRATION CHROMATIQUE MINIMALE
    // Suppression presque totale de la dépendance au kick pour la stabilité
    float shift = (0.002 + iKick * 0.003) * sin(iTime * 2.0);
    float r = texture(iChannel0, distortedUV + vec2(shift, 0.0)).r;
    float g = texture(iChannel0, distortedUV).g;
    float b = texture(iChannel0, distortedUV - vec2(shift, 0.0)).b;
    vec4 tex = vec4(r, g, b, 1.0);
    
    float alpha = texture(iChannel0, distortedUV).a;

    // 4. FLASH LUMINEUX TRÈS SUBTIL
    // Valeur de 0.05 : juste assez pour donner de la vie sans flasher
    tex.rgb += iKick * 0.05 * vec3(0.8, 0.9, 1.0) * alpha;

    // 5. BALAYAGE LUMINEUX (SHINE)
    float shine = smoothstep(0.1, 0.9, sin(distortedUV.x * 2.0 + distortedUV.y + iTime * 2.5));
    tex.rgb += shine * 0.12 * alpha;

    // 6. SCANLINES
    float scanline = sin(gl_FragCoord.y * 1.5) * 0.04;
    tex.rgb -= scanline;

    // 7. VIGNETTAGE
    float vignette = 1.0 - length(centeredUV * 1.5);
    tex.rgb *= pow(vignette, 0.5);

    // 8. FONDU ENCHAÎNÉ (Fade In/Out)
    float segment_dur = 13.33;
    float fade = smoothstep(0.0, 1.5, iTime) * smoothstep(segment_dur, segment_dur - 1.5, iTime);

    fragColor = vec4(tex.rgb, alpha * fade);
}