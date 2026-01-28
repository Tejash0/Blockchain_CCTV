import { Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Record from './pages/Record'
import Verify from './pages/Verify'
import Alerts from './pages/Alerts'

function App() {
  return (
    <div className="min-h-screen">
      {/* Navigation */}
      <nav className="bg-gray-800 text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <span className="text-xl font-bold">CCTV Blockchain</span>
            </div>
            <div className="flex space-x-4">
              <NavLink
                to="/"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-md text-sm font-medium ${
                    isActive ? 'bg-gray-900' : 'hover:bg-gray-700'
                  }`
                }
              >
                Dashboard
              </NavLink>
              <NavLink
                to="/record"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-md text-sm font-medium ${
                    isActive ? 'bg-gray-900' : 'hover:bg-gray-700'
                  }`
                }
              >
                Record
              </NavLink>
              <NavLink
                to="/verify"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-md text-sm font-medium ${
                    isActive ? 'bg-gray-900' : 'hover:bg-gray-700'
                  }`
                }
              >
                Verify
              </NavLink>
              <NavLink
                to="/alerts"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-md text-sm font-medium ${
                    isActive ? 'bg-gray-900' : 'hover:bg-gray-700'
                  }`
                }
              >
                AI Alerts
              </NavLink>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/record" element={<Record />} />
          <Route path="/verify" element={<Verify />} />
          <Route path="/alerts" element={<Alerts />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
