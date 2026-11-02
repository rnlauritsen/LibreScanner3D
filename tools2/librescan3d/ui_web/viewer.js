/* Small self-contained WebGL2 viewer for point clouds and triangle meshes (no libraries, works offline). */
class Viewer {
  constructor(canvas) {
    this.c = canvas; const gl = this.gl = canvas.getContext('webgl2', {antialias: true});
    if (!gl) { this.ok = false; return; } this.ok = true;
    this.yaw = 0.6; this.pitch = 0.35; this.dist = 300; this.target = [0, 0, 0]; this.pointSize = 3; this.mode = 'normal'; this.meshStyle = 'solid';
    this.n = 0; this.nf = 0; this.has = false;
    const vs = `#version 300 es
      in vec3 aPos; in vec3 aNrm; uniform mat4 uMVP; uniform mat3 uNM; uniform float uPS; uniform vec3 uBounds; // min y, max y, size
      out vec3 vN; out float vH;
      void main(){ gl_Position = uMVP*vec4(aPos,1.0); gl_PointSize = uPS; vN = normalize(uNM*aNrm); vH = (aPos.y - uBounds.x)/max(uBounds.y-uBounds.x,1e-6); }`;
    const fs = `#version 300 es
      precision mediump float; in vec3 vN; in float vH; uniform int uMode; uniform int uPoints; uniform int uHasN; out vec4 o;
      vec3 turbo(float t){ t=clamp(t,0.,1.); return clamp(vec3(0.13+4.6*t-12.0*t*t+7.7*t*t*t, 0.09+3.6*t-6.0*t*t+2.5*t*t*t, 0.55+2.0*t-7.5*t*t+7.0*t*t*t-1.8*t*t*t*t),0.,1.); }
      void main(){
        if(uPoints==1){ vec2 d=gl_PointCoord-0.5; if(dot(d,d)>0.25) discard; }
        vec3 n = normalize(vN); float back = 1.0;
        if(uPoints==0 && !gl_FrontFacing){ n=-n; back=0.0; }
        float l = uHasN==1 ? clamp(abs(n.z)*0.75+0.25,0.,1.) : 0.9;
        vec3 base = vec3(0.82);
        if(uMode==1) base = turbo(1.0-vH);
        else if(uMode==2) base = uHasN==1 ? n*0.5+0.5 : vec3(0.8);
        if(uPoints==0 && back<0.5) base = vec3(0.30,0.32,0.38);
        o = vec4(base*l, 1.0); }`;
    const sh = (t, s) => { const x = gl.createShader(t); gl.shaderSource(x, s); gl.compileShader(x); if (!gl.getShaderParameter(x, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(x)); return x; };
    const p = this.prog = gl.createProgram(); gl.attachShader(p, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    this.u = {}; for (const n of ['uMVP', 'uNM', 'uPS', 'uBounds', 'uMode', 'uPoints', 'uHasN']) this.u[n] = gl.getUniformLocation(p, n);
    this.vao = gl.createVertexArray(); this.pb = gl.createBuffer(); this.nb = gl.createBuffer(); this.ib = gl.createBuffer();
    this._bind(); this.dragging = null;
    canvas.addEventListener('mousedown', e => { this.dragging = {x: e.clientX, y: e.clientY, pan: e.button === 2 || e.shiftKey}; e.preventDefault(); });
    window.addEventListener('mouseup', () => this.dragging = null);
    window.addEventListener('mousemove', e => {
      if (!this.dragging) return; const dx = e.clientX - this.dragging.x, dy = e.clientY - this.dragging.y; this.dragging.x = e.clientX; this.dragging.y = e.clientY;
      if (this.dragging.pan) { const s = this.dist * 0.0015; const r = this._right(), u = this._up(); for (let i = 0; i < 3; i++) this.target[i] += (-dx * r[i] + dy * u[i]) * s; }
      else { this.yaw += dx * 0.008; this.pitch = Math.max(-1.55, Math.min(1.55, this.pitch + dy * 0.008)); }
      this.draw(); });
    canvas.addEventListener('wheel', e => { this.dist *= Math.exp(e.deltaY * 0.001); this.draw(); e.preventDefault(); }, {passive: false});
    canvas.addEventListener('contextmenu', e => e.preventDefault());
    canvas.addEventListener('dblclick', () => this.reset());
    new ResizeObserver(() => this.draw()).observe(canvas);
  }
  _bind() { const gl = this.gl; gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.pb); const a = gl.getAttribLocation(this.prog, 'aPos'); gl.enableVertexAttribArray(a); gl.vertexAttribPointer(a, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.nb); const b = gl.getAttribLocation(this.prog, 'aNrm'); gl.enableVertexAttribArray(b); gl.vertexAttribPointer(b, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.ib); }
  // data come in scanner coordinates (x right, y down, z forward); view them upright by turning 180 degrees about x
  setData(buf) {
    const dv = new DataView(buf); const magic = new TextDecoder().decode(new Uint8Array(buf, 0, 4)); if (magic !== 'LS3D') throw new Error('bad data');
    const nv = dv.getUint32(4, true), nf = dv.getUint32(8, true), flags = dv.getUint32(12, true); let o = 16;
    const pos = new Float32Array(buf.slice(o, o + nv * 12)); o += nv * 12; let nrm = null;
    if (flags & 1) { nrm = new Float32Array(buf.slice(o, o + nv * 12)); o += nv * 12; }
    const idx = nf ? new Uint32Array(buf.slice(o, o + nf * 12)) : null;
    const mn = [1e30, 1e30, 1e30], mx = [-1e30, -1e30, -1e30];
    for (let i = 0; i < nv; i++) { pos[3*i+1] = -pos[3*i+1]; pos[3*i+2] = -pos[3*i+2]; for (let k = 0; k < 3; k++) { const v = pos[3*i+k]; if (v < mn[k]) mn[k] = v; if (v > mx[k]) mx[k] = v; } }
    if (nrm) for (let i = 0; i < nv; i++) { nrm[3*i+1] = -nrm[3*i+1]; nrm[3*i+2] = -nrm[3*i+2]; }
    this.bmin = mn; this.bmax = mx; this.n = nv; this.nf = nf; this.hasN = !!nrm; this.has = nv > 0;
    const gl = this.gl; gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.pb); gl.bufferData(gl.ARRAY_BUFFER, pos, gl.STATIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.nb); gl.bufferData(gl.ARRAY_BUFFER, nrm || new Float32Array(nv * 3), gl.STATIC_DRAW);
    if (idx) { gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.ib); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.STATIC_DRAW); }
    this.reset(); return {points: nv, faces: nf, size: mx.map((v, i) => v - mn[i])};
  }
  reset() { if (!this.has) return; const c = [0, 1, 2].map(i => (this.bmin[i] + this.bmax[i]) / 2); this.target = c;
    const s = Math.max(...[0, 1, 2].map(i => this.bmax[i] - this.bmin[i])); this.dist = s * 1.9; this.yaw = 0.5; this.pitch = 0.3; this.draw(); }
  _right() { return [Math.cos(this.yaw), 0, -Math.sin(this.yaw)]; }
  _up() { const cp = Math.cos(this.pitch), sp = Math.sin(this.pitch); return [Math.sin(this.yaw) * sp, cp, Math.cos(this.yaw) * sp]; }
  draw() {
    if (!this.ok) return; const gl = this.gl, c = this.c; const dpr = window.devicePixelRatio || 1;
    const w = Math.max(2, Math.floor(c.clientWidth * dpr)), h = Math.max(2, Math.floor(c.clientHeight * dpr)); if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    gl.viewport(0, 0, w, h); const dark = matchMedia('(prefers-color-scheme: dark)').matches; const bg = dark ? [0.09, 0.10, 0.12] : [0.93, 0.94, 0.96];
    gl.clearColor(bg[0], bg[1], bg[2], 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT); if (!this.has) return;
    gl.enable(gl.DEPTH_TEST); const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw), cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    const eye = [this.target[0] + this.dist * sy * cp, this.target[1] + this.dist * sp, this.target[2] + this.dist * cy * cp];
    const f = norm(sub(this.target, eye)), r = norm(cross(f, [0, 1, 0])), u = cross(r, f);
    const V = [r[0], u[0], -f[0], 0, r[1], u[1], -f[1], 0, r[2], u[2], -f[2], 0, -dot(r, eye), -dot(u, eye), dot(f, eye), 1];
    const near = this.dist * 0.02, far = this.dist * 20, t = 1 / Math.tan(0.4), a = w / h;
    const P = [t / a, 0, 0, 0, 0, t, 0, 0, 0, 0, (far + near) / (near - far), -1, 0, 0, 2 * far * near / (near - far), 0];
    gl.useProgram(this.prog); gl.uniformMatrix4fv(this.u.uMVP, false, mul(P, V));
    gl.uniformMatrix3fv(this.u.uNM, false, [V[0], V[1], V[2], V[4], V[5], V[6], V[8], V[9], V[10]]);
    gl.uniform1f(this.u.uPS, this.pointSize * dpr); gl.uniform3f(this.u.uBounds, this.bmin[1], this.bmax[1], 1);
    gl.uniform1i(this.u.uMode, {flat: 0, height: 1, normal: 2}[this.mode] ?? 0); gl.uniform1i(this.u.uHasN, this.hasN ? 1 : 0);
    gl.bindVertexArray(this.vao);
    if (this.nf && this.meshStyle !== 'points') { gl.uniform1i(this.u.uPoints, 0); gl.disable(gl.CULL_FACE); gl.drawElements(gl.TRIANGLES, this.nf * 3, gl.UNSIGNED_INT, 0); }
    else { gl.uniform1i(this.u.uPoints, 1); gl.drawArrays(gl.POINTS, 0, this.n); }
  }
}
function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; } function dot(a, b) { return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]; }
function cross(a, b) { return [a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0]]; } function norm(a) { const l = Math.hypot(...a) || 1; return [a[0]/l, a[1]/l, a[2]/l]; }
function mul(a, b) { const o = new Array(16).fill(0); for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) for (let k = 0; k < 4; k++) o[c*4+r] += a[k*4+r] * b[c*4+k]; return o; }
