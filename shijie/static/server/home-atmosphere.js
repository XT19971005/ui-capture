/* Homepage-only renderer. Shader snapshot from js/atmosphere.js (2026-10-12).
   Approved settings: rays 140%, softness 100%, disturbance 76%, speed 100%.
   No lab UI, frosted texture, filters, project state or source media dependencies. */
(() => {
  'use strict';
  const canvas = document.getElementById('homeAtmosphere');
  if (!canvas) return;
  const settings = Object.freeze({rayStrength: 140, raySoftness: 100, fogStrength: 76, speed: 100});
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const vertexSource = 'attribute vec2 aPosition; void main(){gl_Position=vec4(aPosition,0.0,1.0);}';
  const fragmentSource = `
    precision highp float;
    uniform vec2 uSize;
    uniform float uTime, uRays, uSoft, uFog;
    float hash(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
    float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);}
    float cloud(vec2 p){return noise(p)*0.67+noise(p*2.07+11.4)*0.33;}
    void main(){
      vec2 screen=vec2(gl_FragCoord.x,uSize.y-gl_FragCoord.y)/uSize;
      vec2 uv=screen*vec2(uSize.x/uSize.y,1.);
      float t=uTime;
      // Whole-screen, low-frequency color fields: broad soft blobs, not ray-shaped fog.
      vec2 drift=vec2(t*.055,-t*.038);
      vec2 warp=vec2(noise(screen*2.2+drift),noise(screen*2.2-drift+9.2))-.5;
      vec2 flow=screen+warp*.38;
      vec2 a=(flow-vec2(.25+.12*sin(t*.13),.28+.10*cos(t*.11)))*vec2(3.5,3.4);
      vec2 b=(flow-vec2(.76+.10*cos(t*.12+2.),.62+.14*sin(t*.10)))*vec2(3.0,3.3);
      vec2 c=(flow-vec2(.23+.10*sin(t*.09+3.),.88+.09*cos(t*.14)))*vec2(3.3,3.7);
      vec2 d=(flow-vec2(.95+.08*sin(t*.11),.12+.12*cos(t*.09)))*vec2(3.9,3.0);
      vec3 color=vec3(.041,.046,.066);
      vec3 gradient=vec3(.16,.12,.14)*exp(-dot(a,a))
        +vec3(.095,.115,.26)*exp(-dot(b,b))
        +vec3(.14,.12,.14)*exp(-dot(c,c))
        +vec3(.095,.115,.25)*exp(-dot(d,d));
      float fogPattern=.76+.72*cloud(flow*1.18+drift*.35);
      color+=gradient*fogPattern*uFog*1.28;
      vec2 ray=uv-vec2(-.13,-.23);
      float radius=length(ray),angle=atan(ray.y,ray.x);
      // Uneven, independently breathing shafts; no repeating sine-stripe fan.
      // Angular noise models moving occluders near the source, while soft spatial
      // density variations dissolve the shafts along their length.
      // All directional light is bounded to the upper-left ~44% by 40% area.
      // Multiplying the complete light contribution also removes long ambient tails.
      float cornerMask=1.-smoothstep(.18,1.,length(screen/vec2(.44,.40)));
      float beams=0.;
      if(cornerMask>0.){
      for(int i=0;i<6;i++){
        float seed=float(i);
        float center=.27+seed*.218+sin(seed*7.31)*.064;
        center+=.048*sin(t*(.18+seed*.012)+seed*2.41);
        center+=(noise(vec2(seed*4.7,t*.17))-.5)*.095;
        float width=mix(.021,.060,uSoft)*( .75+.65*noise(vec2(seed*3.1,t*.13+7.)) );
        float delta=(angle-center)/width;
        float shaft=exp(-delta*delta*.85);
        float breath=.22+.85*noise(vec2(t*.24+seed*5.6,seed*2.8));
        float reach=.85+noise(vec2(seed*2.2,t*.12))*1.15;
        float density=cloud(vec2(radius*2.9-t*.19,angle*8.+seed*.7+t*.055));
        float gaps=smoothstep(.19,.76,density);
        beams+=shaft*breath*(.25+.75*gaps)*exp(-radius/reach);
      }
      float aperture=noise(vec2(angle*9.+t*.035,t*.12));
      float broadLight=cloud(vec2(angle*3.8-t*.055,t*.09+radius*.14));
      float fan=exp(-pow((angle-.86)/.78,4.));
      float light=(beams*.78+broadLight*.18)*fan;
      light*=.65+.35*smoothstep(.12,.8,aperture);
      float source=exp(-radius*3.2)*(.6+.4*noise(vec2(t*.13,6.8)));
      color+=vec3(.32,.338,.36)*(light+source*.35)*uRays*cornerMask;
      }
      color*=1.-.09*smoothstep(.35,.85,length(screen-vec2(.5,.45)));
      // Sub-LSB static dither prevents banding without animated grain/flicker.
      color+=(hash(gl_FragCoord.xy)-.5)/255.;
      gl_FragColor=vec4(color,1.);
    }`;
  let gl, program, buffer, uniforms, lost = false, disposed = false;
  let raf = 0, previous = null, elapsed = 0, accumulated = 0, frames = 0, statsAt = 0;
  const interval = 1000 / 30;

  function stop() {
    cancelAnimationFrame(raf);
    raf = 0;
    previous = null;
    accumulated = 0;
  }
  function release() {
    if (gl && !lost) {
      if (buffer) gl.deleteBuffer(buffer);
      if (program) gl.deleteProgram(program);
    }
    program = buffer = null;
  }
  function fallback(error) {
    stop();
    release();
    canvas.hidden = true;
    canvas.dataset.state = 'fallback';
    console.warn('首页动态背景不可用，保留原静态背景。', error);
  }
  function initialize() {
    gl = canvas.getContext('webgl', {antialias:false, depth:false, stencil:false, preserveDrawingBuffer:true});
    if (!gl) throw Error('WebGL unavailable');
    const shaders = [];
    try {
      for (const [type, source] of [[gl.VERTEX_SHADER, vertexSource], [gl.FRAGMENT_SHADER, fragmentSource]]) {
        const shader = gl.createShader(type);
        shaders.push(shader);
        gl.shaderSource(shader, source);
        gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(shader));
      }
      program = gl.createProgram();
      for (const shader of shaders) gl.attachShader(program, shader);
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
    } finally {
      for (const shader of shaders) gl.deleteShader(shader);
    }
    gl.useProgram(program);
    buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,3,-1,-1,3]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, 'aPosition');
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    uniforms = Object.fromEntries(['uSize','uTime','uRays','uSoft','uFog'].map(name => [name, gl.getUniformLocation(program, name)]));
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.BLEND);
    gl.uniform1f(uniforms.uRays, settings.rayStrength / 100);
    gl.uniform1f(uniforms.uSoft, settings.raySoftness / 100);
    gl.uniform1f(uniforms.uFog, settings.fogStrength / 100);
    canvas.hidden = false;
    for (const [key, value] of Object.entries(settings)) canvas.dataset[key] = String(value);
  }
  function draw() {
    if (!program || lost || disposed) return;
    gl.uniform2f(uniforms.uSize, canvas.width, canvas.height);
    gl.uniform1f(uniforms.uTime, elapsed);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    frames++;
  }
  function resize() {
    if (!program || lost || disposed) return;
    const scale = Math.min(.5, 1100 / Math.max(innerWidth, innerHeight));
    const width = Math.max(1, Math.round(innerWidth * scale));
    const height = Math.max(1, Math.round(innerHeight * scale));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    gl.viewport(0, 0, width, height);
    draw();
  }
  function canAnimate() { return program && !lost && !disposed && !document.hidden && !reduced.matches && !document.querySelector('dialog[open]'); }
  function tick(now) {
    raf = 0;
    if (!canAnimate()) return;
    const delta = previous === null ? 0 : Math.min(now - previous, 100);
    previous = now;
    elapsed += delta / 1000 * (settings.speed / 35);
    accumulated += delta;
    if (accumulated >= interval - .5) {
      accumulated = Math.max(0, accumulated - interval);
      draw();
    }
    if (now - statsAt >= 1000) {
      canvas.dataset.frames = String(frames);
      statsAt = now;
    }
    raf = requestAnimationFrame(tick);
  }
  function schedule() {
    stop();
    if (!program || lost || disposed) return;
    canvas.dataset.state = document.hidden ? 'hidden' : reduced.matches ? 'reduced-motion' : document.querySelector('dialog[open]') ? 'dialog' : 'running';
    if (canAnimate()) raf = requestAnimationFrame(tick);
  }
  canvas.addEventListener('webglcontextlost', event => {
    event.preventDefault();
    lost = true;
    stop();
    canvas.hidden = true;
    canvas.dataset.state = 'context-lost';
  });
  canvas.addEventListener('webglcontextrestored', () => {
    try { lost = false; initialize(); resize(); schedule(); }
    catch (error) { fallback(error); }
  });
  window.addEventListener('resize', resize);
  document.addEventListener('visibilitychange', schedule);
  // Give video preview the GPU while keeping the decorative backdrop's last frame.
  new MutationObserver(schedule).observe(document.body,{subtree:true,attributes:true,attributeFilter:['open']});
  reduced.addEventListener('change', () => { draw(); schedule(); });
  window.addEventListener('pagehide', event => {
    stop();
    if (!event.persisted) { release(); disposed = true; }
  });
  window.addEventListener('pageshow', () => { resize(); schedule(); });
  try { initialize(); resize(); schedule(); }
  catch (error) { fallback(error); }
})();
