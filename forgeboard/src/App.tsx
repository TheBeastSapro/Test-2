import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { StoreProvider } from './lib/store'
import { Shell } from './components/Shell'
import Dashboard from './apps/Dashboard'
import InboxApp from './apps/InboxApp'
import Boards from './apps/Boards'
import CalendarApp from './apps/CalendarApp'
import ChatApp from './apps/ChatApp'
import DriveApp from './apps/DriveApp'
import PayApp from './apps/PayApp'
import InvoicesApp from './apps/InvoicesApp'
import Review from './apps/Review'
import ClientPortal from './apps/ClientPortal'
import ForgeLayout from './apps/forge/ForgeLayout'
import ForgeChat from './apps/forge/ForgeChat'
import Library from './apps/forge/Library'
import Brain from './apps/forge/Brain'
import Automations from './apps/forge/Automations'
import Playground from './apps/forge/Playground'

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
            <Route path="/drive" element={<DriveApp />} />
            <Route path="/review" element={<Review />} />
            <Route path="/pay" element={<PayApp />} />
            <Route path="/invoices" element={<InvoicesApp />} />
            <Route path="/portal" element={<ClientPortal />} />
            <Route path="/forge" element={<ForgeLayout />}>
              <Route index element={<ForgeChat />} />
              <Route path="c/:conversationId" element={<ForgeChat />} />
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
