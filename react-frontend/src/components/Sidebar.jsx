import { NavLink } from 'react-router-dom'
import './Sidebar.css'

function Sidebar() {
  const navItems = [
    { name: 'Patients', path: '/' },
    { name: 'Dashboard', path: '#' },
    { name: 'My Profile', path: '#' },
    { name: 'Messages', path: '#' },
    { name: 'Medical Records', path: '#' },
    { name: 'Documents', path: '#' },
    { name: 'Lab Results', path: '#' },
    { name: 'Payments', path: '#' },
    { name: 'Calendar', path: '#' },
    { name: 'Resources', path: '#' },
    { name: 'FAQ', path: '#' }
  ]

  return (
    <aside className="sidebar">
      <nav className="sidebar-nav">
        <ul>
          {navItems.map((item, index) => (
            <li key={index}>
              {item.path === '#' ? (
                <a href={item.path}>{item.name}</a>
              ) : (
                <NavLink 
                  to={item.path}
                  className={({ isActive }) => isActive ? 'active' : ''}
                >
                  {item.name}
                </NavLink>
              )}
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  )
}

export default Sidebar

