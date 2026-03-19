#version 330
uniform sampler2D iChannelPrev;
uniform sampler2D iChannelNext;
uniform float     iTransition;
uniform vec2      iResolution;
out vec4 fragColor;

void main() {
    vec2 uv  = gl_FragCoord.xy / iResolution;
    float s  = smoothstep(0.0, 1.0, iTransition);

    // Tri de pixels : décaler verticalement selon la luminosité
    vec4 colA = texture(iChannelPrev, uv);
    float lum = dot(colA.rgb, vec3(0.299, 0.587, 0.114));
    float shift = lum * s * 0.4;
    vec2 uvSort = uv + vec2(0.0, shift);
    uvSort = clamp(uvSort, vec2(0.0), vec2(1.0));

    vec4 a = texture(iChannelPrev, uvSort);
    vec4 b = texture(iChannelNext, uv);

    // Frange lumineuse au front de la transition
    float front = smoothstep(0.03, 0.0, abs(uv.y - (1.0 - s)));
    vec3  col   = mix(a.rgb, b.rgb, smoothstep(0.0, 1.0, s));
    col += front * 0.8;

    fragColor = vec4(col, 1.0);
}
