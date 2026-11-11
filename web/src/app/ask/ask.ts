import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { catchError, finalize, of } from 'rxjs';
import { Api, AskResponse } from '../api';

interface Ticket extends AskResponse { question: string; flipped: boolean; }

const LIVE_SUGGESTIONS = [
  'Which stations are empty most often?',
  'At what hour do stations run out?',
  'What share of bikes are electric?',
];

@Component({
  selector: 'app-ask',
  imports: [FormsModule],
  templateUrl: './ask.html',
  styleUrl: './ask.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Ask {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  protected readonly staticDemo = this.api.staticDemo;
  protected readonly question = signal('');
  protected readonly tickets = signal<Ticket[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  private readonly saved = toSignal(
    this.staticDemo ? this.api.getSavedAnswers().pipe(catchError(() => of([]))) : of([]), { initialValue: [] });
  protected readonly suggestions = computed(() =>
    this.staticDemo ? this.saved().map(answer => answer.question) : LIVE_SUGGESTIONS);

  protected send(text = this.question()): void {
    const question = text.trim();
    if (question.length < 3 || this.loading()) { return; }
    this.loading.set(true);
    this.error.set(null);
    this.api.ask(question).pipe(finalize(() => this.loading.set(false))).subscribe({
      next: answer => {
        this.tickets.update(list => [{ ...answer, question, flipped: false }, ...list.filter(t => t.question !== question)]);
        this.question.set('');
      },
      error: failure => this.error.set(
        failure.status === 'static' ? 'This online demo only has the saved questions below. Run the project locally to ask your own.'
          : failure.status === 429 ? 'You’ve reached the question limit. Try again later.'
            : 'The question didn’t go through. Check that the API is running, then send it again.'),
    });
  }

  protected columns(ticket: Ticket): string[] {
    return Object.keys(ticket.rows[0] ?? {}).filter(key => key !== 'station_id');
  }

  protected heading(key: string): string {
    return key.includes('(') || key.startsWith('f0_') ? 'Result' : key.replace(/_/g, ' ');
  }

  protected cell(value: unknown): string {
    if (typeof value === 'number') {
      return value.toLocaleString('en-GB', { maximumFractionDigits: 1 });
    }
    return String(value ?? '');
  }

  protected flip(ticket: Ticket): void {
    this.tickets.update(list => list.map(item => item === ticket ? { ...item, flipped: !item.flipped } : item));
  }

  protected showOnMap(ticket: Ticket): void {
    this.api.highlighted.set(ticket.station_ids);
    this.router.navigateByUrl('/');
  }
}
