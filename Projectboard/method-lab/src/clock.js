// Gemeinsame Abspielzeit für 3D-Szene und Oberfläche, ohne React-Rendering je Frame.
export const clock = {
  t: 0, playing: true, rate: 1,
  advance(dt, run) {
    if (!this.playing) return;
    this.t += Math.min(dt, .1) * this.rate;
    if (this.t >= (run.frames - 1) * run.dt + .9) this.t = 0;
  },
  time(run) { return Math.min(this.t, (run.frames - 1) * run.dt); },
};
