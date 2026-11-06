import {
  afterNextRender, ChangeDetectionStrategy, Component, DestroyRef, effect, ElementRef,
  inject, input, output, viewChild,
} from '@angular/core';
import { Station } from '../api';

const MINT = '#8fe3b0';
const AMBER = '#f4b740';
const RED = '#ff5468';
const WHITE = '#ffffff';
const HIT_RADIUS = 16;
const LOW_SHARE = 0.15;

/** The city, drawn only from station positions. The river appears as the gap in the dots. */
@Component({
  selector: 'app-city-canvas',
  template: `<canvas #canvas role="img" [attr.aria-label]="label()" (click)="pick($event)"
    (pointermove)="hover($event)"></canvas>`,
  styles: `
    :host { display: block; position: absolute; inset: 0; }
    canvas { display: block; width: 100%; height: 100%; touch-action: manipulation; }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CityCanvas {
  readonly stations = input.required<Station[]>();
  /** Bikes per station, in the same order as stations. */
  readonly bikes = input.required<(number | null)[]>();
  readonly selectedId = input<number | null>(null);
  readonly highlighted = input<number[]>([]);
  readonly label = input('');
  /** Space kept clear at the bottom and right for the overlaid controls. */
  readonly inset = input({ top: 0, bottom: 0, right: 0 });
  readonly picked = output<number | null>();

  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private context: CanvasRenderingContext2D | null = null;
  private points: { x: number; y: number }[] = [];
  private sprites = new Map<string, HTMLCanvasElement>();
  private width = 0;
  private height = 0;
  private ready = false;

  constructor() {
    const destroyRef = inject(DestroyRef);
    afterNextRender(() => {
      const element = this.canvas().nativeElement;
      this.context = element.getContext('2d');
      const observer = new ResizeObserver(() => this.resize());
      observer.observe(element);
      destroyRef.onDestroy(() => observer.disconnect());
      this.ready = true;
      this.resize();
    });
    effect(() => { this.stations(); this.inset(); if (this.ready) { this.project(); } });
    effect(() => {
      this.bikes(); this.selectedId(); this.highlighted(); this.stations(); this.inset();
      if (this.ready) { this.draw(); }
    });
  }

  private resize(): void {
    const element = this.canvas().nativeElement;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    this.width = element.clientWidth;
    this.height = element.clientHeight;
    element.width = Math.round(this.width * ratio);
    element.height = Math.round(this.height * ratio);
    this.context?.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.project();
    this.draw();
  }

  private project(): void {
    const stations = this.stations();
    if (!stations.length || !this.width) { return; }
    const lats = stations.map(s => s.lat);
    const lons = stations.map(s => s.lon);
    const [south, north, west, east] = [Math.min(...lats), Math.max(...lats), Math.min(...lons), Math.max(...lons)];
    const squeeze = Math.cos((south + north) / 2 * Math.PI / 180);
    const margin = 24;
    const room = { w: this.width - this.inset().right - margin * 2, h: this.height - this.inset().top - this.inset().bottom - margin * 2 };
    const scale = Math.min(room.w / ((east - west) * squeeze), room.h / (north - south));
    const left = margin + (room.w - (east - west) * squeeze * scale) / 2;
    const top = this.inset().top + margin + (room.h - (north - south) * scale) / 2;
    this.points = stations.map(s => ({
      x: left + (s.lon - west) * squeeze * scale,
      y: top + (north - s.lat) * scale,
    }));
  }

  private sprite(color: string): HTMLCanvasElement {
    let sprite = this.sprites.get(color);
    if (!sprite) {
      sprite = document.createElement('canvas');
      sprite.width = sprite.height = 64;
      const c = sprite.getContext('2d')!;
      const glow = c.createRadialGradient(32, 32, 0, 32, 32, 32);
      glow.addColorStop(0, color);
      glow.addColorStop(0.28, color + 'aa');
      glow.addColorStop(1, color + '00');
      c.fillStyle = glow;
      c.fillRect(0, 0, 64, 64);
      this.sprites.set(color, sprite);
    }
    return sprite;
  }

  private draw(): void {
    const c = this.context;
    const stations = this.stations();
    const bikes = this.bikes();
    if (!c || this.points.length !== stations.length) { return; }
    c.clearRect(0, 0, this.width, this.height);
    const unit = Math.max(0.75, Math.min(this.width, this.height) / 800);
    const lit = new Set(this.highlighted());
    c.globalCompositeOperation = 'lighter';
    for (let i = 0; i < stations.length; i++) {
      const count = bikes[i];
      const point = this.points[i];
      if (count === null || count === undefined) {
        c.globalAlpha = 0.18;
        c.drawImage(this.sprite(MINT), point.x - 2, point.y - 2, 4, 4);
        continue;
      }
      const share = count / Math.max(stations[i].capacity, 1);
      const empty = count < 0.5;
      const color = empty ? RED : share < LOW_SHARE ? AMBER : MINT;
      const size = (empty ? 10 : 4 + 9 * Math.sqrt(Math.min(share, 1))) * unit;
      c.globalAlpha = empty ? 0.95 : 0.34 + 0.5 * Math.min(share, 1);
      c.drawImage(this.sprite(color), point.x - size / 2, point.y - size / 2, size, size);
    }
    c.globalCompositeOperation = 'source-over';
    c.globalAlpha = 1;
    this.points.forEach((point, i) => {
      if (lit.has(stations[i].station_id)) { this.ring(point, 8 * unit, WHITE, 1.5); }
    });
    const chosen = stations.findIndex(s => s.station_id === this.selectedId());
    if (chosen >= 0) { this.ring(this.points[chosen], 11 * unit, WHITE, 2.5); }
  }

  private ring(point: { x: number; y: number }, radius: number, color: string, width: number): void {
    const c = this.context!;
    c.beginPath();
    c.arc(point.x, point.y, radius, 0, Math.PI * 2);
    c.strokeStyle = color;
    c.lineWidth = width;
    c.stroke();
  }

  private nearest(event: MouseEvent): number {
    const box = this.canvas().nativeElement.getBoundingClientRect();
    const x = event.clientX - box.left;
    const y = event.clientY - box.top;
    let best = -1;
    let bestDistance = HIT_RADIUS ** 2;
    this.points.forEach((point, i) => {
      const distance = (point.x - x) ** 2 + (point.y - y) ** 2;
      if (distance < bestDistance) { best = i; bestDistance = distance; }
    });
    return best;
  }

  protected pick(event: MouseEvent): void {
    const index = this.nearest(event);
    this.picked.emit(index >= 0 ? this.stations()[index].station_id : null);
  }

  protected hover(event: MouseEvent): void {
    this.canvas().nativeElement.style.cursor = this.nearest(event) >= 0 ? 'pointer' : 'default';
  }
}
