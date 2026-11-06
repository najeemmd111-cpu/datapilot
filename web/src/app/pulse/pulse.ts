import { ChangeDetectionStrategy, Component, computed, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { catchError, debounceTime, distinctUntilChanged, filter, map, of, startWith, switchMap } from 'rxjs';
import { Api, Prediction, Replay, Station } from '../api';
import { CityCanvas } from './city-canvas';
import { Heartbeat } from './heartbeat';
import { StationPanel } from './station-panel';

const SECONDS_PER_DAY = 40;

@Component({
  selector: 'app-pulse',
  imports: [CityCanvas, Heartbeat, StationPanel],
  templateUrl: './pulse.html',
  styleUrl: './pulse.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Pulse {
  protected readonly api = inject(Api);
  protected readonly meta = toSignal(this.api.getMeta().pipe(catchError(() => of(null))));
  private readonly stationState = toSignal(this.api.getStations().pipe(
    map(list => ({ stations: list.stations, failed: false })),
    catchError(() => of({ stations: [] as Station[], failed: true })),
  ));
  protected readonly stations = computed(() => this.stationState()?.stations ?? []);
  protected readonly failed = computed(() => this.stationState()?.failed ?? false);

  protected readonly day = signal<string | null>(null);
  protected readonly position = signal(0);
  protected readonly playing = signal(false);
  protected readonly selectedId = signal<number | null>(null);
  protected readonly search = signal('');
  private readonly narrow = signal(window.matchMedia('(max-width: 760px)').matches);

  private readonly replay = toSignal(toObservable(this.day).pipe(
    filter((day): day is string => day !== null),
    switchMap(day => this.api.getReplay(day).pipe(catchError(() => of(null)), startWith(undefined))),
  ));

  /** Maps each station to its column, because a day may not include every station. */
  private readonly columns = computed(() => {
    const replay = this.replay();
    if (!replay) { return [] as number[]; }
    const index = new Map(replay.station_ids.map((id, column) => [id, column]));
    return this.stations().map(station => index.get(station.station_id) ?? -1);
  });

  protected readonly slotCount = computed(() => this.replay()?.slots.length ?? 0);
  protected readonly slotIndex = computed(() => Math.min(Math.round(this.position()), Math.max(this.slotCount() - 1, 0)));
  protected readonly slot = computed(() => this.replay()?.slots[this.slotIndex()] ?? null);
  protected readonly clock = computed(() => this.time(this.slot()));
  protected readonly dayLabel = computed(() => this.day() ? this.formatDay(this.day()!) : '');

  protected readonly currentBikes = computed(() => {
    const replay = this.replay();
    if (!replay) { return this.stations().map(() => null); }
    const position = Math.min(this.position(), replay.slots.length - 1);
    const first = replay.bikes[Math.floor(position)];
    const second = replay.bikes[Math.ceil(position)] ?? first;
    const fraction = position % 1;
    return this.columns().map(column => {
      if (column < 0) { return null; }
      const a = first[column];
      const b = second[column] ?? a;
      return a === null || b === null ? a ?? b : a + (b - a) * fraction;
    });
  });

  /** Share of stations with no bikes in each slot: the line along the bottom. */
  protected readonly pulse = computed(() => {
    const replay = this.replay();
    if (!replay) { return [] as number[]; }
    return replay.bikes.map(row => {
      const seen = row.filter(value => value !== null);
      return seen.filter(value => value === 0).length / Math.max(seen.length, 1);
    });
  });
  protected readonly emptyNow = computed(() => Math.round((this.pulse()[this.slotIndex()] ?? 0) * this.stations().length));

  protected readonly selected = computed(() => this.stations().find(s => s.station_id === this.selectedId()) ?? null);
  private readonly selectedColumn = computed(() => this.replay()?.station_ids.indexOf(this.selectedId() ?? -1) ?? -1);
  protected readonly history = computed(() => {
    const column = this.selectedColumn();
    return column < 0 ? [] : this.replay()!.bikes.map(row => row[column]);
  });
  protected readonly labels = computed(() => (this.replay()?.slots ?? []).map(slot => this.time(slot)));
  protected readonly selectedBikes = computed(() => {
    const column = this.selectedColumn();
    return column < 0 ? null : this.replay()!.bikes[this.slotIndex()][column];
  });

  private readonly predictionRequest = computed(() => {
    const id = this.selectedId();
    const slot = this.slot();
    return id !== null && slot && !this.playing() ? `${id}|${slot}` : null;
  });
  private readonly predictionState = toSignal(toObservable(this.predictionRequest).pipe(
    distinctUntilChanged(),
    switchMap(request => {
      if (!request) { return of({ result: null as Prediction | null, error: null as string | null }); }
      const [id, slot] = request.split('|');
      return of(null).pipe(debounceTime(200), switchMap(() => this.api.getPrediction(+id, slot)),
        map(result => ({ result, error: null })),
        catchError(failure => of({
          result: null,
          error: failure.status === 404 ? 'This station has no reading at this time.' : 'The chance of running out isn’t available right now.',
        })),
        startWith({ result: null, error: null }));
    }),
  ));
  protected readonly prediction = computed(() => this.predictionState()?.result ?? null);
  protected readonly predictionError = computed(() => this.predictionState()?.error ?? null);

  protected readonly matches = computed(() => {
    const text = this.search().trim().toLowerCase();
    return text.length < 2 ? [] : this.stations().filter(s => s.name.toLowerCase().includes(text)).slice(0, 6);
  });
  protected readonly inset = computed(() => {
    const bottom = this.narrow() ? 180 : 142;
    return { top: this.narrow() ? 150 : 0, bottom, right: this.selected() && !this.narrow() ? 364 : 0 };
  });

  private frame = 0;
  private lastTime = 0;

  constructor() {
    const destroyRef = inject(DestroyRef);
    const media = window.matchMedia('(max-width: 760px)');
    const onChange = () => this.narrow.set(media.matches);
    media.addEventListener('change', onChange);
    destroyRef.onDestroy(() => { cancelAnimationFrame(this.frame); media.removeEventListener('change', onChange); });

    effect(() => {
      const days = this.meta()?.days;
      if (days?.length && untracked(this.day) === null) {
        // The last day is often partial, so open on the last full one.
        this.day.set(days.at(days.length > 2 ? -2 : -1)!);
      }
    });
    let started = false;
    effect(() => {
      if (this.slotCount() && !started) {
        started = true;
        this.position.set(Math.min(23, this.slotCount() - 1));
        if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) { this.play(); }
      }
    });
  }

  protected toggle(): void {
    if (this.playing()) { this.pause(); } else { this.play(); }
  }

  private play(): void {
    if (this.position() >= this.slotCount() - 1) { this.position.set(0); }
    this.playing.set(true);
    this.lastTime = performance.now();
    this.frame = requestAnimationFrame(now => this.step(now));
  }

  private pause(): void {
    this.playing.set(false);
    cancelAnimationFrame(this.frame);
  }

  private step(now: number): void {
    if (!this.playing()) { return; }
    const elapsed = Math.min(now - this.lastTime, 100) / 1000;
    this.lastTime = now;
    const end = this.slotCount() - 1;
    const next = this.position() + (elapsed / SECONDS_PER_DAY) * this.slotCount();
    if (next >= end) { this.position.set(end); this.pause(); return; }
    this.position.set(next);
    this.frame = requestAnimationFrame(later => this.step(later));
  }

  protected scrub(value: number): void {
    this.pause();
    this.position.set(value);
  }

  protected chooseDay(value: string): void {
    this.day.set(value);
  }

  protected choose(id: number | null): void {
    this.selectedId.set(id);
    if (id !== null) { this.pause(); }
    this.search.set('');
  }

  protected clearHighlights(): void { this.api.highlighted.set([]); }

  protected formatDay(day: string): string {
    return new Date(`${day}T12:00:00Z`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' });
  }

  private time(slot: string | null): string {
    if (!slot) { return '--:--'; }
    return new Date(slot).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Paris' });
  }
}
