import { useState } from 'react';
import { DemoTask } from './DemoTask';
import { Credentials } from './Credentials';

type View = 'task' | 'credentials';

export function App() {
  const [view, setView] = useState<View>('task');

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">AgentSwitch</span>
          <span className="brand-tag">Milestone 1 · simulated agents</span>
        </div>
        <nav className="nav" aria-label="Main">
          <button
            type="button"
            className={view === 'task' ? 'nav-item is-active' : 'nav-item'}
            aria-current={view === 'task' ? 'page' : undefined}
            onClick={() => setView('task')}
          >
            New Task
          </button>
          <button
            type="button"
            className={view === 'credentials' ? 'nav-item is-active' : 'nav-item'}
            aria-current={view === 'credentials' ? 'page' : undefined}
            onClick={() => setView('credentials')}
          >
            Credentials
          </button>
        </nav>
      </header>

      <main className="main">
        {view === 'task' ? <DemoTask /> : <Credentials />}
      </main>
    </div>
  );
}
