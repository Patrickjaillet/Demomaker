#version 330
uniform sampler2D iChannel0; // L'image PNG
uniform vec2 iResolution;
uniform float iTime;         // Temps global
uniform float iLocalTime;    // Temps depuis le début de l'affichage de l'image
uniform float iDuration;     // Durée totale de l'image
out vec4 fragColor;

void main() {
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    
    // On remet l'image à l'endroit (car Pygame/GL inversent parfois Y)
    // Si ton image est à l'envers, retire ou ajoute "1.0 - uv.y"
    vec4 col = texture(iChannel0, uv);
    
    // Calcul de l'opacité (Fade In et Fade Out de 1 seconde)
    float fade = smoothstep(0.0, 1.0, iLocalTime) * smoothstep(iDuration, iDuration - 1.0, iLocalTime);
    
    fragColor = col * fade;
}