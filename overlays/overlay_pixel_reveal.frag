#version 330
uniform sampler2D iChannel0;
uniform vec2 iResolution;
uniform float iLocalTime;
uniform float iDuration;
out vec4 fragColor;

void main() {
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    
    // Calcul de la taille des pixels : de 50px à 1px
    float progress = iLocalTime / iDuration;
    float pixelSize = mix(50.0, 1.0, smoothstep(0.0, 0.3, progress));
    
    vec2 puv = floor(uv * iResolution.xy / pixelSize) / (iResolution.xy / pixelSize);
    vec4 col = texture(iChannel0, puv);
    
    float fade = smoothstep(0.0, 0.2, iLocalTime) * smoothstep(iDuration, iDuration - 0.2, iLocalTime);
    fragColor = col * fade;
}