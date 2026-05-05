import React, { useState, useEffect } from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Header from "./components/Header";
import LandingPage from "./pages/LandingPage";
import Dashboard from "./pages/Dashboard";
import SessionView from "./pages/SessionView";
import Analytics from "./pages/Analytics";
import Users from "./pages/Users";
import StreamingDashboard from "./pages/StreamingDashboard";

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Check if user is already authenticated
    const currentParticipant = localStorage.getItem('currentParticipant');
    if (currentParticipant) {
      setIsAuthenticated(true);
    }
    setIsLoading(false);
  }, []);

  // Listen for authentication changes
  useEffect(() => {
    const handleStorageChange = () => {
      const currentParticipant = localStorage.getItem('currentParticipant');
      setIsAuthenticated(!!currentParticipant);
    };

    window.addEventListener('storage', handleStorageChange);
    
    // Also check periodically for localStorage changes (for same-tab updates)
    const interval = setInterval(() => {
      const currentParticipant = localStorage.getItem('currentParticipant');
      if (currentParticipant && !isAuthenticated) {
        setIsAuthenticated(true);
      }
    }, 100);

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      clearInterval(interval);
    };
  }, [isAuthenticated]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-400 mx-auto mb-4"></div>
          <p className="text-white text-lg">Loading RTAPS...</p>
        </div>
      </div>
    );
  }

  return (
    <Router>
      {!isAuthenticated ? (
        <LandingPage />
      ) : (
        <div className="min-h-screen bg-gray-50">
          <Header />
          <main className="container mx-auto px-4 py-6">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/session/:procedureId" element={<SessionView />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/users" element={<Users />} />
              <Route path="/streaming" element={<StreamingDashboard />} />
            </Routes>
          </main>
        </div>
      )}
    </Router>
  );
}

export default App;
