import { Routes } from '@angular/router';
import { Ask } from './ask/ask';
import { Pulse } from './pulse/pulse';

export const routes: Routes = [
  { path: '', component: Pulse, title: 'Paris Pulse' },
  { path: 'ask', component: Ask, title: 'Ask the city · Paris Pulse' },
  { path: '**', redirectTo: '' },
];
