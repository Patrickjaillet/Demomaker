#version 330
uniform sampler2D iChannelPrev;
uniform sampler2D iChannelNext;
uniform float     iTransition;
uniform vec2      iResolution;
out vec4 fragColor;

void main() {
    vec2  uv  = gl_FragCoord.xy / iResolution;
    float s   = smoothstep(0.0, 1.0, iTransition);
    float edge = smoothstep(s - 0.02, s + 0.02, uv.x);
    vec4  a   = texture(iChannelPrev, uv);
    vec4  b   = texture(iChannelNext, uv);
    // Frange lumineuse sur le wipe
    float glow = smoothstep(0.025, 0.0, abs(uv.x - s)) * 1.5;
    vec3  col  = mix(a.rgb, b.rgb, edge) + glow;
    fragColor  = vec4(col, 1.0);
}
