import { HttpClient } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { map, Observable, shareReplay, switchMap, throwError } from 'rxjs';
import { environment } from '../environments/environment';

export interface Meta { mode: 'sample' | 'real' | 'bigquery'; days: string[]; llm: string | null; staticDemo?: boolean; }
export interface Station {
  station_id: number; name: string; lat: number; lon: number; capacity: number;
  bikes: number | null; docks: number | null;
}
export interface StationList { as_of: string; stations: Station[]; }
export interface Replay {
  date: string; slots: string[]; station_ids: number[]; bikes: (number | null)[][];
  /** Static demo only: chance of no bikes in 30 minutes, as a whole percent. */
  risk?: (number | null)[][];
}
export interface Prediction { station_id: number; as_of: string; bikes: number; empty_in_30_min: number; }
export interface AskResponse {
  answer: string; sql: string | null; rows: Record<string, unknown>[];
  station_ids: number[]; uses_llm: boolean; saved?: boolean;
}
export interface SavedAnswer extends AskResponse { question: string; model: string; }

@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);
  readonly staticDemo = environment.staticDemo;
  /** Stations named by the last answer, shown lit up on the city page. */
  readonly highlighted = signal<number[]>([]);
  private readonly replays = new Map<string, Observable<Replay>>();
  private savedAnswers?: Observable<SavedAnswer[]>;

  getMeta(): Observable<Meta> {
    return this.http.get<Meta>(this.staticDemo ? 'data/meta.json' : '/api/meta');
  }

  getStations(): Observable<StationList> {
    return this.http.get<StationList>(this.staticDemo ? 'data/stations.json' : '/api/stations');
  }

  getReplay(date: string): Observable<Replay> {
    if (!this.staticDemo) { return this.http.get<Replay>('/api/replay', { params: { date } }); }
    if (!this.replays.has(date)) {
      this.replays.set(date, this.http.get<Replay>(`data/replay/${date}.json`).pipe(shareReplay(1)));
    }
    return this.replays.get(date)!;
  }

  getPrediction(stationId: number, slot: string): Observable<Prediction> {
    if (!this.staticDemo) {
      return this.http.get<Prediction>('/api/predict', { params: { station_id: stationId, slot } });
    }
    const day = new Date(slot).toLocaleDateString('en-CA', { timeZone: 'Europe/Paris' });
    return this.getReplay(day).pipe(switchMap(replay => {
      const row = replay.slots.indexOf(slot);
      const column = replay.station_ids.indexOf(stationId);
      const risk = row < 0 || column < 0 ? null : replay.risk?.[row][column] ?? null;
      const bikes = row < 0 || column < 0 ? null : replay.bikes[row][column];
      if (risk === null || bikes === null) { return throwError(() => ({ status: 404 })); }
      return [{ station_id: stationId, as_of: slot, bikes, empty_in_30_min: risk / 100 }];
    }));
  }

  /** Static demo only: real questions answered earlier by Gemini, with their SQL and results. */
  getSavedAnswers(): Observable<SavedAnswer[]> {
    this.savedAnswers ??= this.http.get<SavedAnswer[]>('data/answers.json').pipe(shareReplay(1));
    return this.savedAnswers;
  }

  ask(question: string): Observable<AskResponse> {
    if (!this.staticDemo) { return this.http.post<AskResponse>('/api/ask', { question }); }
    const wanted = question.trim().toLowerCase();
    return this.getSavedAnswers().pipe(map(answers => {
      const found = answers.find(answer => answer.question.toLowerCase() === wanted);
      if (!found) { throw { status: 'static' }; }
      return found;
    }));
  }
}
