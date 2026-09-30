import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Home from './pages/Home';
import Admin from './pages/Admin';
import Sources from './pages/Sources';
import Imports from './pages/Imports';

const qc = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/admin/sources" element={<Sources />} />
          <Route path="/admin/imports" element={<Imports />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
