#version 330
uniform sampler2D iChannelPrev;
uniform sampler2D iChannelNext;
uniform float     iTransition;
uniform vec2      iResolution;
out vec4 fragColor;

void main() {
    vec2 uv  = gl_FragCoord.xy / iResolution;
    vec2 c   = uv - 0.5;
    float s  = smoothstep(0.0, 1.0, iTransition);

    // Zoom-blur radial : la scène précédente explose vers l'extérieur
    const int STEPS = 8;
    vec4 acc = vec4(0.0);
    float scale_start = 1.0 + s * 0.5;
    for (int i = 0; i < STEPS; i++) {
        float sc  = mix(scale_start, 1.0, float(i) / float(STEPS - 1));
        vec2  suv = c / sc + 0.5;
        suv = clamp(suv, vec2(0.0), vec2(1.0));
        acc += texture(iChannelPrev, suv);
    }
    acc /= float(STEPS);

    vec4 b = texture(iChannelNext, uv);
    fragColor = mix(acc, b, s * s);
}
