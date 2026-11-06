import {
  afterRenderEffect, ChangeDetectionStrategy, Component, computed, DestroyRef, ElementRef,
  inject, input, output, viewChild,
} from '@angular/core';
import {
  CategoryScale, Chart, Filler, LinearScale, LineController, LineElement, PointElement, Tooltip,
} from 'chart.js';
import { Prediction, Station } from '../api';

Chart.register(CategoryScale, Filler, LinearScale, LineController, LineElement, PointElement, Tooltip);

const RING_RADIUS = 54;

/** The Last Bike panel: one station's day, and its chance of running out. */
@Component({
  selector: 'app-station-panel',
  templateUrl: './station-panel.html',
  styleUrl: './station-panel.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StationPanel {
  readonly station = input.required<Station>();
  readonly bikesNow = input<number | null>(null);
  readonly history = input.required<(number | null)[]>();
  readonly labels = input.required<string[]>();
  readonly prediction = input<Prediction | null>(null);
  readonly predictionError = input<string | null>(null);
  readonly playing = input(false);
  readonly closed = output<void>();

  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('chart');
  private chart: Chart | null = null;
  protected readonly radius = RING_RADIUS;
  protected readonly circumference = 2 * Math.PI * RING_RADIUS;
  protected readonly percent = computed(() => Math.round((this.prediction()?.empty_in_30_min ?? 0) * 100));
  protected readonly percentText = computed(() => {
    const chance = this.prediction()?.empty_in_30_min ?? 0;
    return chance < 0.01 ? 'Under 1%' : `${this.percent()}%`;
  });
  protected readonly ringColor = computed(() => {
    const value = this.percent();
    return value >= 50 ? 'var(--empty)' : value >= 20 ? 'var(--low)' : 'var(--rim)';
  });
  protected readonly dash = computed(() => `${(this.percent() / 100) * this.circumference} ${this.circumference}`);

  constructor() {
    inject(DestroyRef).onDestroy(() => this.chart?.destroy());
    afterRenderEffect(() => {
      const history = this.history();
      const labels = this.labels();
      if (!this.chart) {
        this.chart = new Chart(this.canvas().nativeElement, {
          type: 'line',
          data: { labels, datasets: [{
            data: history, borderColor: '#8fe3b0', backgroundColor: '#8fe3b022', fill: true,
            pointRadius: 0, borderWidth: 2, tension: 0.25, spanGaps: true,
          }] },
          options: {
            animation: false, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: { displayColors: false, callbacks: { label: item => `${item.formattedValue} bikes` } } },
            scales: {
              x: { grid: { display: false }, ticks: { color: '#aebbdf', maxTicksLimit: 5, maxRotation: 0 } },
              y: { min: 0, grid: { color: '#ffffff14' }, ticks: { color: '#aebbdf', maxTicksLimit: 4, precision: 0 } },
            },
          },
        });
      } else {
        this.chart.data.labels = labels;
        this.chart.data.datasets[0].data = history;
        this.chart.update('none');
      }
    });
  }
}
