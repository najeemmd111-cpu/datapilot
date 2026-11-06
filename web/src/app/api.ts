import { HttpClient } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { Observable } from 'rxjs';

export interface Meta { mode: 'sample' | 'real' | 'bigquery'; days: string[]; llm: string | null; }
export interface Station {
  station_id: number; name: string; lat: number; lon: number; capacity: number;
  bikes: number | null; docks: number | null;
}
export interface StationList { as_of: string; stations: Station[]; }
export interface Replay { date: string; slots: string[]; station_ids: number[]; bikes: (number | null)[][]; }
export interface Prediction { station_id: number; as_of: string; bikes: number; empty_in_30_min: number; }
export interface AskResponse {
  answer: string; sql: string | null; rows: Record<string, unknown>[];
  station_ids: number[]; uses_llm: boolean;
}

@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);
  /** Stations named by the last answer, shown lit up on the city page. */
  readonly highlighted = signal<number[]>([]);

  getMeta(): Observable<Meta> { return this.http.get<Meta>('/api/meta'); }
  getStations(): Observable<StationList> { return this.http.get<StationList>('/api/stations'); }
  getReplay(date: string): Observable<Replay> { return this.http.get<Replay>('/api/replay', { params: { date } }); }
  getPrediction(stationId: number, slot: string): Observable<Prediction> {
    return this.http.get<Prediction>('/api/predict', { params: { station_id: stationId, slot } });
  }
  ask(question: string): Observable<AskResponse> { return this.http.post<AskResponse>('/api/ask', { question }); }
}
