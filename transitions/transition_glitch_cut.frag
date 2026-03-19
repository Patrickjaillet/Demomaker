#version 330
uniform sampler2D iChannelPrev;
uniform sampler2D iChannelNext;
uniform float     iTransition;
uniform float     iTime;
uniform vec2      iResolution;
out vec4 fragColor;

float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }

void main() {
    vec2 uv  = gl_FragCoord.xy / iResolution;
    float s  = smoothstep(0.0, 1.0, iTransition);

    // Bloc glitch : partitionner en tranches horizontales décalées
    float slice   = floor(uv.y * 24.0);
    float glitchT = floor(iTime * 18.0);
    float offset  = (hash(vec2(slice, glitchT)) - 0.5) * 0.08
                    * sin(iTransition * 3.14159) * 2.0;
    vec2 uvA = uv + vec2(offset, 0.0);
    vec2 uvB = uv - vec2(offset * 0.5, 0.0);

    vec4 a = texture(iChannelPrev, fract(uvA));
    vec4 b = texture(iChannelNext, fract(uvB));

    // Aberration chromatique en milieu de transition
    float ca = sin(iTransition * 3.14159) * 0.012;
    a.r = texture(iChannelPrev, fract(uvA + vec2( ca,0))).r;
    b.b = texture(iChannelNext, fract(uvB - vec2( ca,0))).b;

    fragColor = mix(a, b, s);
}
