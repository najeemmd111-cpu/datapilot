import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';
import { Api, AskResponse } from '../api';

interface Ticket extends AskResponse { question: string; flipped: boolean; }

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
  protected readonly question = signal('');
  protected readonly tickets = signal<Ticket[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly suggestions = [
    'Which stations are empty most often?',
    'At what hour do stations run out?',
    'What share of bikes are electric?',
  ];

  protected send(text = this.question()): void {
    const question = text.trim();
    if (question.length < 3 || this.loading()) { return; }
    this.loading.set(true);
    this.error.set(null);
    this.api.ask(question).pipe(finalize(() => this.loading.set(false))).subscribe({
      next: answer => {
        this.tickets.update(list => [{ ...answer, question, flipped: false }, ...list]);
        this.question.set('');
      },
      error: failure => this.error.set(
        failure.status === 429 ? 'You’ve reached the question limit. Try again in an hour.'
          : 'The question didn’t go through. Check that the API is running, then send it again.'),
    });
  }

  protected flip(ticket: Ticket): void {
    this.tickets.update(list => list.map(item => item === ticket ? { ...item, flipped: !item.flipped } : item));
  }

  protected showOnMap(ticket: Ticket): void {
    this.api.highlighted.set(ticket.station_ids);
    this.router.navigateByUrl('/');
  }
}
