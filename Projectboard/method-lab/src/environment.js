// Prozedurale HDR-Umgebungen, ohne Download. Lichtquellen sind weiche Rechtecke auf der Kugel.
import * as THREE from 'three';

// Jedes Licht: Azimut und Höhe in Grad, Halbbreite und Halbhöhe in Grad, Leuchtkraft, Farbe.
export const ENVIRONMENTS = {
  foto: {label: 'Labor, generiertes Panorama', photo: 'textures/env_labor.jpg', top: [.3, .3, .3], bottom: [.15, .15, .15], lights: []},
  labor: {label: 'Labor, Deckenpanels', top: [.035, .042, .052], bottom: [.008, .009, .011], lights: [
    ...[-120, -60, 0, 60, 120, 180].map(a => [a, 62, 14, 8, 5.5, [1, .98, .94]]),
    [90, 12, 40, 8, .4, [.75, .85, 1]],
  ]},
  studio: {label: 'Studio, drei Softboxen', top: [.03, .03, .035], bottom: [.008, .008, .01], lights: [
    [45, 45, 22, 26, 24, [1, .97, .92]],
    [-70, 25, 16, 32, 7, [.82, .9, 1]],
    [175, 40, 30, 12, 12, [1, 1, 1]],
  ]},
  fenster: {label: 'Tageslicht, Fensterfront', top: [.26, .3, .36], bottom: [.05, .045, .04], lights: [
    [30, 26, 34, 24, 34, [1, .96, .88]],
    [30, 60, 5, 5, 300, [1, .93, .8]],
  ]},
  nacht: {label: 'Nachtlabor, Akzentlicht', top: [.012, .016, .03], bottom: [.003, .004, .006], lights: [
    [80, 18, 10, 36, 16, [.25, .7, 1]],
    [-100, 22, 10, 36, 12, [1, .45, .3]],
    [0, 75, 22, 12, 7, [.9, .94, 1]],
  ]},
};

const smooth = (edge, soft, v) => Math.min(1, Math.max(0, (edge + soft - v) / (2 * soft)));

// Das Panorama ist ein 8-Bit-Bild. Die hellsten Bereiche werden hochgerechnet, damit Leuchten und Fenster
// wie Lichtquellen wirken; das ist geschätzt, kein gemessenes HDR.
function loadPhoto(tex, url) {
  const img = new Image();
  img.onload = () => {
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const ctx = c.getContext('2d', {willReadFrequently: true});
    ctx.drawImage(img, 0, 0);
    const src = ctx.getImageData(0, 0, c.width, c.height).data;
    const px = new Float32Array(c.width * c.height * 4);
    for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
      const i = (y * c.width + x) * 4, o = ((c.height - 1 - y) * c.width + x) * 4;
      const r = Math.pow(src[o] / 255, 2.2), g = Math.pow(src[o + 1] / 255, 2.2), b = Math.pow(src[o + 2] / 255, 2.2);
      const lum = .2126 * r + .7152 * g + .0722 * b;
      const t = Math.min(1, Math.max(0, (lum - .7) / .3));
      const boost = .3 * (1 + 9 * t * t * t);
      px[i] = r * boost; px[i + 1] = g * boost; px[i + 2] = b * boost; px[i + 3] = 1;
    }
    tex.image = {data: px, width: c.width, height: c.height};
    tex.dispose();
    tex.needsUpdate = true;
    tex.needsPMREMUpdate = true;
  };
  img.src = url;
}

export function makeEnvironment(name) {
  const def = ENVIRONMENTS[name] || ENVIRONMENTS.labor;
  const W = 1024, H = 512, px = new Float32Array(W * H * 4);
  for (let y = 0; y < H; y++) {
    const elev = (y + .5) / H * 180 - 90;
    const g = Math.max(0, Math.min(1, (elev + 25) / 110));
    for (let x = 0; x < W; x++) {
      const az = (x + .5) / W * 360 - 180;
      let r = def.bottom[0] + (def.top[0] - def.bottom[0]) * g;
      let gr = def.bottom[1] + (def.top[1] - def.bottom[1]) * g;
      let b = def.bottom[2] + (def.top[2] - def.bottom[2]) * g;
      for (const [la, le, hw, hh, power, c] of def.lights) {
        let da = Math.abs(az - la); if (da > 180) da = 360 - da;
        const w = smooth(hw, 2.5, da * Math.max(.2, Math.cos(elev * Math.PI / 180))) * smooth(hh, 2.5, Math.abs(elev - le));
        r += w * power * c[0]; gr += w * power * c[1]; b += w * power * c[2];
      }
      const i = (y * W + x) * 4;
      px[i] = r; px[i + 1] = gr; px[i + 2] = b; px[i + 3] = 1;
    }
  }
  const tex = new THREE.DataTexture(px, W, H, THREE.RGBAFormat, THREE.FloatType);
  tex.mapping = THREE.EquirectangularReflectionMapping;
  tex.minFilter = tex.magFilter = THREE.LinearFilter;
  tex.wrapS = THREE.RepeatWrapping;
  tex.colorSpace = THREE.LinearSRGBColorSpace;
  tex.needsUpdate = true;
  if (def.photo) loadPhoto(tex, def.photo);
  return tex;
}

// Näherung nach Tanner Helland, gültig etwa von 1000 bis 12000 K.
export function kelvinColor(k) {
  const t = k / 100;
  const r = t <= 66 ? 255 : 329.698727446 * Math.pow(t - 60, -.1332047592);
  const g = t <= 66 ? 99.4708025861 * Math.log(t) - 161.1195681661 : 288.1221695283 * Math.pow(t - 60, -.0755148492);
  const b = t >= 66 ? 255 : t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  const c = v => Math.max(0, Math.min(255, v)) / 255;
  return new THREE.Color().setRGB(c(r), c(g), c(b), THREE.SRGBColorSpace);
}
