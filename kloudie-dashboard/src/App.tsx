import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { StoreProvider } from './lib/store'
import { Shell } from './components/Shell'
import Dashboard from './apps/Dashboard'
import InboxApp from './apps/InboxApp'
import Boards from './apps/Boards'
import CalendarApp from './apps/CalendarApp'
import ChatApp from './apps/ChatApp'
import FilesApp from './apps/FilesApp'
import EconomyApp from './apps/EconomyApp'
import ClientPortal from './apps/ClientPortal'
import KloudieLayout from './apps/kloudie/KloudieLayout'
import KloudieChat from './apps/kloudie/KloudieChat'
import Library from './apps/kloudie/Library'
import Brain from './apps/kloudie/Brain'
import Automations from './apps/kloudie/Automations'
import Playground from './apps/kloudie/Playground'

export default function App() {
  return (
    <StoreProvider>
      <HashRouter>
        <Shell>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/inbox" element={<InboxApp />} />
            <Route path="/boards" element={<Boards />} />
            <Route path="/boards/:boardId" element={<Boards />} />
            <Route path="/calendar" element={<CalendarApp />} />
            <Route path="/chat" element={<ChatApp />} />
            <Route path="/files" element={<FilesApp />} />
            <Route path="/economy" element={<EconomyApp />} />
            <Route path="/portal" element={<ClientPortal />} />
            <Route path="/kloudie" element={<KloudieLayout />}>
              <Route index element={<KloudieChat />} />
              <Route path="c/:conversationId" element={<KloudieChat />} />
              <Route path="library" element={<Library />} />
              <Route path="brain" element={<Brain />} />
              <Route path="automations" element={<Automations />} />
              <Route path="playground" element={<Playground />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Shell>
      </HashRouter>
    </StoreProvider>
  )
}
