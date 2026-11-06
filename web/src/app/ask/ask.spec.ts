import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Ask } from './ask';

describe('Ask', () => {
  beforeEach(() => TestBed.configureTestingModule({
    imports: [Ask], providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
  }));

  it('shows the answer and flips to the generated SQL', async () => {
    const fixture = TestBed.createComponent(Ask);
    await fixture.whenStable();
    const page = fixture.nativeElement as HTMLElement;
    page.querySelector<HTMLButtonElement>('.try button')!.click();
    TestBed.inject(HttpTestingController).expectOne('/api/ask').flush({
      answer: 'Sample Bastille 1 comes first', sql: 'SELECT 1', rows: [], station_ids: [1], uses_llm: false,
    });
    await fixture.whenStable();
    expect(page.querySelector('.answer')?.textContent).toContain('Sample Bastille 1');
    page.querySelector<HTMLButtonElement>('.front .actions button')!.click();
    await fixture.whenStable();
    expect(page.querySelector('.ticket')?.classList).toContain('flipped');
    expect(page.querySelector('pre')?.textContent).toContain('SELECT 1');
  });

  it('explains when the question limit is reached', async () => {
    const fixture = TestBed.createComponent(Ask);
    await fixture.whenStable();
    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.try button')!.click();
    TestBed.inject(HttpTestingController).expectOne('/api/ask').flush('Too many', { status: 429, statusText: 'Limit' });
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).querySelector('.error')?.textContent).toContain('question limit');
  });
});
