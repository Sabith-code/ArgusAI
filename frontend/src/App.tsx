import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { DashboardPage } from './pages/DashboardPage';
import { MentionsPage } from './pages/MentionsPage';
import { EventsPage } from './pages/EventsPage';
import { SignalsPage } from './pages/SignalsPage';

function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/mentions" element={<MentionsPage />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/signals" element={<SignalsPage />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}

export default App;
