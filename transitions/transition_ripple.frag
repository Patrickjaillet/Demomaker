#version 330
uniform sampler2D iChannelPrev;
uniform sampler2D iChannelNext;
uniform float     iTransition;
uniform float     iTime;
uniform vec2      iResolution;
out vec4 fragColor;

void main() {
    vec2 uv  = gl_FragCoord.xy / iResolution;
    vec2 c   = uv - 0.5;
    float r  = length(c);
    float s  = smoothstep(0.0, 1.0, iTransition);

    // Onde de choc depuis le centre
    float wave   = sin((r - s * 1.4) * 28.0 - iTime * 4.0)
                   * (1.0 - s) * 0.025
                   * exp(-r * 3.0);
    vec2 uvWarp  = uv + normalize(c + 0.001) * wave;
    uvWarp = clamp(uvWarp, vec2(0.0), vec2(1.0));

    vec4 a = texture(iChannelPrev, uvWarp);
    vec4 b = texture(iChannelNext, uv);

    // Masque circulaire s'élargissant
    float mask = smoothstep(s * 1.4 - 0.05, s * 1.4, r);
    fragColor  = mix(b, a, mask);
}
