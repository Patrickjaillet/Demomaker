#version 330
uniform sampler2D iChannel0;
uniform vec2 iResolution;
uniform float iLocalTime;
uniform float iDuration;
out vec4 fragColor;

mat2 rot(float a) { float c=cos(a), s=sin(a); return mat2(c,s,-s,c); }

void main() {
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    vec2 center = uv - 0.5;
    
    float dist = length(center);
    float progress = smoothstep(0.0, 1.0, iLocalTime * 0.5);
    
    // Spirale basée sur la distance au centre
    float angle = (1.0 - progress) * 5.0 * dist;
    vec2 spiralUV = rot(angle) * center;
    
    // Zoom progressif
    spiralUV /= max(progress, 0.001);
    spiralUV += 0.5;
    
    vec4 col = vec4(0.0);
    if(spiralUV.x >= 0.0 && spiralUV.x <= 1.0 && spiralUV.y >= 0.0 && spiralUV.y <= 1.0) {
        col = texture(iChannel0, spiralUV);
    }
    
    float fade = smoothstep(0.0, 0.5, iLocalTime) * smoothstep(iDuration, iDuration - 0.5, iLocalTime);
    fragColor = col * fade;
}