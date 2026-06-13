import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom'
import ConnectPage from './pages/ConnectPage'
import DashboardPage from './pages/DashboardPage'

export default function App() {
  return (
    <Routes>
      <Route path="/"          element={<ConnectPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="*"          element={<Navigate to="/" replace />} />
    </Routes>
  )
}