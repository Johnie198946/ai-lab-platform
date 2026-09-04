import { Renderer, Program, Mesh, Triangle, Texture } from 'ogl';
import { useEffect, useRef } from 'react';
import './EvilEye.css';

function hexToVec3(hex) {
  const h = hex.replace('#', '');
  return [
    parseInt(h.substring(0, 2), 16) / 255,
    parseInt(h.substring(2, 4), 16) / 255,
    parseInt(h.substring(4, 6), 16) / 255,
  ];
}

const vert = `
attribute vec2 position;
attribute vec2 uv;
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

const frag = `
precision highp float;
uniform float uTime;
uniform vec2 uResolution;
uniform vec2 uMouse;
uniform vec3 uColor;
uniform float uIntensity;
uniform float uPupilSize;
uniform float uIrisWidth;
uniform float uGlowIntensity;
uniform float uScale;
uniform float uNoiseScale;
uniform float uPupilFollow;
uniform float uFlameSpeed;
uniform vec3 uBackgroundColor;

varying vec2 vUv;

// Noise functions
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec2 mod289(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec3 permute(vec3 x) { return mod289(((x*34.0)+1.0)*x); }

float snoise(vec2 v) {
    const vec4 C = vec4(0.211324865405187,  // (3.0-sqrt(3.0))/6.0
                        0.366025403784439,  // 0.5*(sqrt(3.0)-1.0)
                        -0.577350269189626, // -1.0 + 2.0 * C.x
                        0.024390243902439); // 1.0 / 41.0
    vec2 i  = floor(v + dot(v, C.yy) );
    vec2 x0 = v -   i + dot(i, C.xx);
    vec2 i1;
    i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;
    i = mod289(i);
    vec3 p = permute( permute( i.y + vec3(0.0, i1.y, 1.0 ))
        + i.x + vec3(0.0, i1.x, 1.0 ));
    vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy), dot(x12.zw,x12.zw)), 0.0);
    m = m*m ;
    m = m*m ;
    vec3 x = 2.0 * fract(p * C.www) - 1.0;
    vec3 h = abs(x) - 0.5;
    vec3 ox = floor(x + 0.5);
    vec3 a0 = x - ox;
    m *= 1.79284291400159 - 0.85373472095314 * ( a0*a0 + h*h );
    vec3 g;
    g.x  = a0.x  * x0.x  + h.x  * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;
    return 130.0 * dot(m, g);
}

float fbm(vec2 x) {
    float v = 0.0;
    float a = 0.5;
    vec2 shift = vec2(100.0);
    mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.50));
    for (int i = 0; i < 5; ++i) {
        v += a * snoise(x);
        x = rot * x * 2.0 + shift;
        a *= 0.5;
    }
    return v;
}

void main() {
    vec2 uv = (vUv - 0.5) * 2.0;
    uv.x *= uResolution.x / uResolution.y;
    
    // Scale the entire coordinate system
    uv *= (1.0 / uScale);
    
    // Mouse interaction for pupil
    vec2 mouseOffset = (uMouse * 2.0 - 1.0) * uPupilFollow;
    
    // Background space with swirling noise
    vec2 spaceUv = uv * uNoiseScale;
    float n1 = fbm(spaceUv + uTime * 0.05);
    float n2 = fbm(spaceUv - uTime * 0.08 + vec2(n1));
    
    // Eye geometry
    float r = length(uv);
    float angle = atan(uv.y, uv.x);
    
    // Distorted coordinates for organic feel
    vec2 distortedUv = uv + vec2(
        fbm(uv * 2.0 + uTime * uFlameSpeed) * 0.1,
        fbm(uv * 2.0 - uTime * uFlameSpeed) * 0.1
    );
    float distortedR = length(distortedUv);
    
    // Pupil (pure black)
    vec2 pupilUv = uv - mouseOffset;
    float pupilR = length(pupilUv);
    
    // Iris
    float irisShape = fbm(uv * 3.0 - uTime * 0.1);
    float iris = smoothstep(uPupilSize + uIrisWidth, uPupilSize, distortedR + irisShape * 0.1);
    iris *= smoothstep(uPupilSize, uPupilSize + 0.1, pupilR); // clear pupil area
    
    // Outer glow / flames
    float flameShape = fbm(vec2(angle * 3.0, distortedR * 2.0 - uTime * uFlameSpeed));
    float glow = exp(-distortedR * (3.0 - uGlowIntensity)) * flameShape;
    
    // Eye shape (almond)
    float eyeShape = 1.0 - smoothstep(0.0, 1.5, abs(uv.y) + abs(uv.x) * 0.5);
    
    // Color compositing
    vec3 pupilColor = vec3(0.0); // Pure black pupil
    
    // Create rich iris colors
    vec3 irisBase = uColor;
    vec3 irisDetail = mix(uColor, vec3(0.4, 0.4, 0.5), fbm(uv * 10.0));
    vec3 finalIris = mix(irisBase, irisDetail, irisShape) * uIntensity;
    
    // Glow color
    vec3 glowColor = uColor * glow * uIntensity;
    
    // Background noise color
    vec3 bgNoise = uBackgroundColor + vec3(n2 * 0.05);
    
    // Mix it all together
    vec3 color = bgNoise;
    
    // Add glow
    color += glowColor;
    
    // Add iris
    color = mix(color, finalIris, iris * eyeShape);
    
    // Add pupil (make it perfectly smooth, no noise distortion)
    float cleanPupil = smoothstep(uPupilSize, uPupilSize - 0.01, pupilR);
    color = mix(color, pupilColor, cleanPupil);
    
    // Add subtle caustic/light reflection
    float reflection = smoothstep(0.8, 1.0, fbm(uv * 3.0 + uTime)) * 0.5;
    color += reflection * iris;

    gl_FragColor = vec4(color, 1.0);
}
`;

export default function EvilEye({
  eyeColor = '#ff3300',
  intensity = 1.5,
  pupilSize = 0.15,
  irisWidth = 0.4,
  glowIntensity = 1.0,
  scale = 1.0,
  noiseScale = 1.0,
  pupilFollow = 0.1,
  flameSpeed = 1.0,
  backgroundColor = '#120F17'
}) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const renderer = new Renderer({
      dpr: Math.min(window.devicePixelRatio, 2),
      alpha: true,
    });
    
    const gl = renderer.gl;
    containerRef.current.appendChild(gl.canvas);

    const program = new Program(gl, {
      vertex: vert,
      fragment: frag,
      uniforms: {
        uTime: { value: 0 },
        uResolution: { value: [0, 0] },
        uMouse: { value: [0.5, 0.5] },
        uColor: { value: hexToVec3(eyeColor) },
        uIntensity: { value: intensity },
        uPupilSize: { value: pupilSize },
        uIrisWidth: { value: irisWidth },
        uGlowIntensity: { value: glowIntensity },
        uScale: { value: scale },
        uNoiseScale: { value: noiseScale },
        uPupilFollow: { value: pupilFollow },
        uFlameSpeed: { value: flameSpeed },
        uBackgroundColor: { value: hexToVec3(backgroundColor) }
      },
    });

    const geometry = new Triangle(gl);
    const mesh = new Mesh(gl, { geometry, program });

    let animationId;
    
    const handleResize = () => {
      const { clientWidth, clientHeight } = containerRef.current;
      renderer.setSize(clientWidth, clientHeight);
      program.uniforms.uResolution.value = [clientWidth, clientHeight];
    };

    const handleMouseMove = (e) => {
      const rect = containerRef.current.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width;
      const y = 1.0 - (e.clientY - rect.top) / rect.height;
      program.uniforms.uMouse.value = [x, y];
    };

    window.addEventListener('resize', handleResize);
    containerRef.current.addEventListener('mousemove', handleMouseMove);
    handleResize();

    const render = (t) => {
      program.uniforms.uTime.value = t * 0.001;
      renderer.render({ scene: mesh });
      animationId = requestAnimationFrame(render);
    };

    animationId = requestAnimationFrame(render);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (containerRef.current) {
        containerRef.current.removeEventListener('mousemove', handleMouseMove);
        containerRef.current.removeChild(gl.canvas);
      }
      cancelAnimationFrame(animationId);
    };
  }, [eyeColor, intensity, pupilSize, irisWidth, glowIntensity, scale, noiseScale, pupilFollow, flameSpeed, backgroundColor]);

  return <div ref={containerRef} className="evil-eye-container" />;
}
