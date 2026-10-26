/*! Grainient field adapted from React Bits / Grainient.
 * Copyright (c) 2026 David Haz. MIT + Commons Clause.
 * Source: https://github.com/DavidHDev/react-bits/blob/e12c22192ac7b4b452c5e2feb9b586d74765d696/src/content/Backgrounds/Grainient/Grainient.jsx
 * Full notice: react-bits-LICENSE.md.
 * Keeps the upstream domain warp, mirrored bands, Oklab ramp, silk shading,
 * and fine/clumped grain. BEND: a fixed petrol/jade/ivory palette, hero-relative
 * coordinates, title protection, and a soft light that follows the material.
 */
export const fluxVertex = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0., 1.);
}
`;

export const fluxFragment = /* glsl */ `
precision highp float;
uniform float uTime, uAspect, uViewScale, uNarrow, uPresence, uDpr;
uniform vec2 uPointer;
varying vec2 vUv;

// Deliberately retain Grainient's substantial, interleaving colour
// regions. A two-band ramp folds back through its palette as the field drifts.
const float BANDS = 2.15;
const float SOFTNESS = .82;
const float FLOW = 2.15;
const float SCALE = .86;
const float SILK = .40;
const vec2 DIRECTION = vec2(.819152, -.573576);

vec2 hash2(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * vec3(.1031, .103, .0973));
  q += dot(q, q.yzx + 33.33);
  return fract((q.xx + q.yz) * q.zy) * 2. - 1.;
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * f * (f * (f * 6. - 15.) + 10.);
  float a = dot(hash2(i), f);
  float b = dot(hash2(i + vec2(1., 0.)), f - vec2(1., 0.));
  float c = dot(hash2(i + vec2(0., 1.)), f - vec2(0., 1.));
  float d = dot(hash2(i + vec2(1.)), f - vec2(1.));
  return .5 + .5 * mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

vec2 drift(vec2 p, float t) {
  vec2 w1 = vec2(
    noise(p * .85 + vec2(t * .11, t * .07)),
    noise(p * .85 + vec2(4.1, 1.7) - vec2(t * .08, t * .12))
  );
  vec2 w2 = vec2(
    noise(p * 1.55 + w1 * 1.8 + vec2(1.3, 7.1) + t * .05),
    noise(p * 1.55 + w1 * 1.8 + vec2(6.4, 2.2) - t * .06)
  );
  return (w1 - .5) * 1.1 + (w2 - .5) * .55;
}

vec2 warp(vec2 p) {
  // Upstream's time is advanced at .16 real seconds; this is slightly calmer.
  float t = uTime * .13 + 2.3;
  vec2 q = p / SCALE;
  q += vec2(-DIRECTION.y, DIRECTION.x) * t * .45;
  return p + drift(q + vec2(3.17, 1.91), t) * FLOW * SCALE;
}

float coord(vec2 p) {
  float extent = uAspect * abs(DIRECTION.x) + abs(DIRECTION.y);
  return dot(warp(p), DIRECTION) / extent + .5;
}

// Oklab values calculated from the listed sRGB colours. Interpolation and the
// small relief adjustment happen in perceptual space, as in upstream Grainient.
vec3 ramp(float index) {
  if (index < .5) return vec3(.2408334, -.0296391, -.0081115); // #0b2424
  if (index < 1.5) return vec3(.3403471, -.0417287, -.0132243); // #183f40
  if (index < 2.5) return vec3(.5361897, -.0588739,  .0012295); // #45796e
  if (index < 3.5) return vec3(.6792713, -.0277629,  .0098325); // #899e92
  return vec3(.8335019, -.0118584, .0163987);                 // #c5cbbd
}

vec3 labToRgb(vec3 lab) {
  float l = lab.x + .3963377774 * lab.y + .2158037573 * lab.z;
  float m = lab.x - .1055613458 * lab.y - .0638541728 * lab.z;
  float s = lab.x - .0894841775 * lab.y - 1.2914855480 * lab.z;
  l = l * l * l;
  m = m * m * m;
  s = s * s * s;
  return vec3(
    4.0767416621 * l - 3.3077115913 * m + .2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - .3413193965 * s,
    -.0041960863 * l - .7034186147 * m + 1.7076147010 * s
  );
}

vec3 encode(vec3 c) {
  c = clamp(c, 0., 1.);
  return mix(c * 12.92, 1.055 * pow(c, vec3(1. / 2.4)) - .055,
             step(.0031308, c));
}

float grainHash(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * .1031);
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}

float clump(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3. - 2. * f);
  return mix(mix(grainHash(i), grainHash(i + vec2(1., 0.)), u.x),
             mix(grainHash(i + vec2(0., 1.)), grainHash(i + vec2(1.)), u.x), u.y);
}

void main() {
  vec2 screen = vec2(vUv.x, (1. - vUv.y) * uViewScale);
  vec2 world = vec2(screen.x * uAspect, screen.y);
  vec2 origin = vec2(uAspect * .55, mix(.50, .72, uNarrow));
  vec2 p = world - origin;

  float raw = coord(p);
  float s = raw * BANDS;
  float cycle = floor(s);
  s = fract(s);
  if (mod(cycle, 2.) > .5) s = 1. - s;
  s = clamp(s, 0., 1.);
  float scaled = s * 4.;
  float index = min(floor(scaled), 3.);
  float f = scaled - index;
  float edge = max(SOFTNESS * .5, fwidth(scaled) * .75);
  float shaped = smoothstep(.5 - edge, .5 + edge, f);
  vec3 lab = mix(ramp(index), ramp(index + 1.), shaped);

  // Screen derivatives recover the field's slope without evaluating its
  // nested noise twice more. Divide by world pixel size to preserve lighting
  // across resolutions, including the inverted vertical screen coordinate.
  vec2 grad = vec2(dFdx(raw) / max(dFdx(world.x), .000001),
                   dFdy(raw) / min(dFdy(world.y), -.000001));
  vec2 slope = grad * sin(3.14159265 * clamp(raw, 0., 1.) * BANDS) * SILK * 4.;
  vec3 normal = normalize(vec3(-slope, 1.));
  vec3 light = normalize(vec3(-DIRECTION.y, DIRECTION.x, 1.2));
  float diffuse = dot(normal, light) - light.z;
  lab = ramp(0.) + (lab - ramp(0.)) *
    (1. + (diffuse * .35 + max(diffuse, 0.) * diffuse * .6) * SILK);

  // The hand brings a soft light close to the surface. Its footprint follows
  // the local fold, with a long, feathered edge along the material rather than
  // a circular cursor halo. The underlying field and its normals never move.
  vec2 acrossFold = normalize(grad + vec2(.00001));
  vec2 alongFold = vec2(-acrossFold.y, acrossFold.x);
  vec2 fromHand = world - uPointer;
  float along = dot(fromHand, alongFold);
  float across = dot(fromHand, acrossFold);
  float softbox = exp(-.5 * (along * along / .2116 + across * across / .0400));
  float material = smoothstep(.018, .24, length(slope));
  vec3 cursorLight = normalize(vec3(-fromHand + vec2(-.14, -.12), .55));
  float facing = .55 + .45 * max(0., dot(normal, cursorLight));
  float caughtLight = softbox * material * facing;
  // A much softer shaded shoulder gives the response depth. Both tones follow
  // existing folds and disappear outside the immediate working area.
  float shoulder = exp(-.5 * (along * along / .3025 +
                              (across + .23) * (across + .23) / .0900));
  float lift = (.105 * caughtLight - .023 * shoulder * material) * uPresence;
  // Whole-Oklab scaling is multiplicative RGB lighting: hue and chromaticity
  // stay intact. The response is bounded by construction, including fast input.
  lab *= (lab.x + lift) / lab.x;
  vec3 colour = encode(labToRgb(lab));

  // Preserve the material's broad shape on the right, while the ordinary DOM
  // heading retains the same dark ground and unchanged layout as the live page.
  float clear = mix(smoothstep(.38, .83, screen.x),
                    smoothstep(.43, .84, screen.y), uNarrow);
  float exposure = mix(.095, .80, clear);
  float masthead = mix(.42, 1., smoothstep(.07, .36, screen.y));
  // Let the same material catch a little light beneath the quiet title area,
  // while keeping the heading comfortably brighter than its background.
  exposure = mix(exposure, max(exposure, .23), caughtLight * uPresence);
  colour = mix(vec3(.033, .079, .075), colour, exposure * masthead);

  // Upstream's fine/clumped composite is retained in the same pass. Grain is
  // screen-locked so the material feels tactile without animated-film flicker.
  vec2 pixel = gl_FragCoord.xy / max(uDpr, 1.);
  float fine = grainHash(pixel) + grainHash(pixel + 7.13) - 1.;
  float coarse = (clump(pixel / 1.6) - .5) * 2.;
  float grain = mix(fine, coarse, .48);
  float luma = dot(colour, vec3(.2126, .7152, .0722));
  colour += grain * .048 * (.45 + 2.2 * luma * (1. - luma));
  gl_FragColor = vec4(clamp(colour, 0., 1.), 1.);
}
`;
