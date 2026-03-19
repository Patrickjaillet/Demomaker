#version 330
uniform sampler2D iChannel0; // La texture du texte (très large)
uniform vec2 iResolution;
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
uniform sampler2D iWaveform;  // unit 9 — waveform  [0,1]
out vec4 fragColor;

void main() {
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    
    // 1. Définir la zone du bandeau (en bas de l'écran, hauteur 15%)
    float bandHeight = 0.15;
    if (uv.y > bandHeight) discard; // On ne dessine rien au dessus du bandeau

    // 2. Vitesse du défilement
    float speed = 0.2;
    float scroll = iTime * speed;
    
    // 3. Effet d'ondulation (Sinus)
    // On déforme le Y du texte en fonction du X
    float wave = sin(uv.x * 10.0 + iTime * 5.0) * 0.1;
    
    // 4. Mapping des coordonnées
    // On étire l'UV pour ne voir qu'une partie de la longue texture de texte
    vec2 textUV;
    textUV.x = fract(uv.x * 0.5 + scroll); // Le fract permet de boucler le texte
    textUV.y = (uv.y / bandHeight) + wave; 

    // 5. Lecture de la texture
    vec4 col = texture(iChannel0, textUV);
    
    // 6. Effets de couleur Techno
    // Le texte change de couleur sur le Kick
    vec3 colorA = vec3(0.0, 0.8, 1.0); // Cyan
    vec3 colorB = vec3(1.0, 0.0, 0.5); // Magenta
    col.rgb *= mix(colorA, colorB, iKick);
    
    // Effet de scanline sur le texte
    col.rgb *= 0.8 + 0.2 * sin(gl_FragCoord.y * 2.0);

    fragColor = col;
}