import { NavLink, Outlet } from 'react-router-dom'

function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">◆</span> SmartSupport
        </div>
        <nav className="nav">
          <NavLink to="/intake" className={({ isActive }) => (isActive ? 'active' : '')}>
            Mail Intake
          </NavLink>
          <NavLink to="/review" className={({ isActive }) => (isActive ? 'active' : '')}>
            Agent Review
          </NavLink>
          <NavLink to="/dashboard" className={({ isActive }) => (isActive ? 'active' : '')}>
            Dashboard
          </NavLink>
        </nav>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}

export default App
