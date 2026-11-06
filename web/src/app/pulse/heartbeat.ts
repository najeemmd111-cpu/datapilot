import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

const WIDTH = 1000;
const HEIGHT = 84;

/** The city's pulse: the share of empty stations through the day. Doubles as the time control. */
@Component({
  selector: 'app-heartbeat',
  template: `
    <svg [attr.viewBox]="'0 0 ' + width + ' ' + height" preserveAspectRatio="none" aria-hidden="true">
      <path class="fill" [attr.d]="area()" />
      <path class="line" [attr.d]="line()" vector-effect="non-scaling-stroke" />
      <line class="now" [attr.x1]="cursor()" [attr.x2]="cursor()" y1="0" [attr.y2]="height"
        vector-effect="non-scaling-stroke" />
    </svg>
    <input type="range" min="0" [max]="max()" step="0.01" [value]="position()" [attr.aria-label]="label()"
      [attr.aria-valuetext]="valueText()" (input)="moved.emit(+$any($event.target).value)" />
  `,
  styles: `
    :host { display: block; position: relative; height: 84px; }
    svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
    .fill { fill: var(--empty); opacity: .16; }
    .line { fill: none; stroke: var(--empty); stroke-width: 2.5; stroke-linejoin: round; }
    .now { stroke: var(--plaque); stroke-width: 2; }
    input {
      position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: ew-resize;
    }
    :host(:focus-within) svg { outline: 3px solid var(--low); outline-offset: 3px; }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Heartbeat {
  readonly values = input.required<number[]>();
  readonly position = input.required<number>();
  readonly label = input('Time of day');
  readonly valueText = input('');
  readonly moved = output<number>();
  protected readonly width = WIDTH;
  protected readonly height = HEIGHT;
  protected readonly max = computed(() => Math.max(this.values().length - 1, 0));
  private readonly coordinates = computed(() => {
    const values = this.values();
    const top = Math.max(...values, 0.0001);
    return values.map((value, i) => [
      (i / Math.max(values.length - 1, 1)) * WIDTH, HEIGHT - 4 - (value / top) * (HEIGHT - 12),
    ]);
  });
  protected readonly line = computed(() =>
    this.coordinates().map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(''));
  protected readonly area = computed(() => this.line() ? `${this.line()}L${WIDTH} ${HEIGHT}L0 ${HEIGHT}Z` : '');
  protected readonly cursor = computed(() => (this.position() / Math.max(this.max(), 1)) * WIDTH);
}
