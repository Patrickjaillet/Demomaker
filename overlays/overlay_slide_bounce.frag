#version 330
uniform sampler2D iChannel0;
uniform vec2 iResolution;
uniform float iLocalTime;
uniform float iDuration;
out vec4 fragColor;

void main() {
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    
    // Formule de rebond (Overshoot)
    float t = clamp(iLocalTime * 1.5, 0.0, 2.0);
    float offset = 1.0 - (sin(t * 2.0) / exp(t * 1.5)); // Glisse de 1.0 à 0.0 avec rebond
    
    vec2 slideUV = uv;
    slideUV.x += (1.0 - offset); // Décalage horizontal
    
    vec4 col = vec4(0.0);
    if(slideUV.x >= 0.0 && slideUV.x <= 1.0) {
        col = texture(iChannel0, slideUV);
    }
    
    float fade = smoothstep(iDuration, iDuration - 0.5, iLocalTime);
    fragColor = col * fade;
}