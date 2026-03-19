#version 330
uniform sampler2D iChannelPrev;
uniform sampler2D iChannelNext;
uniform float     iTransition;   // [0..1]
uniform vec2      iResolution;
out vec4 fragColor;

void main() {
    vec2 uv = gl_FragCoord.xy / iResolution;
    vec4 a  = texture(iChannelPrev, uv);
    vec4 b  = texture(iChannelNext, uv);
    float s = smoothstep(0.0, 1.0, iTransition);
    fragColor = mix(a, b, s);
}
