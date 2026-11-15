/**
 * Header — global navbar with a large standalone Team/Project logo.
 *
 * - Logo image: src/assets/logo.png (registered in src/assets/index.js)
 */
import { Link, NavLink } from 'react-router-dom';
import { ASSETS } from '../../assets';
import { PROJECT } from '../../config/project';
import { ROUTES } from '../../router/routes';
import './Header.css';

export default function Header() {
  return (
    <header className="site-header">
      <Link to={ROUTES.home} className="site-header__brand" aria-label={`${PROJECT.name} — home`}>
        {/* TEAM / PROJECT LOGO — fills the full brand slot without side text */}
        <img src={ASSETS.logo} alt={`${PROJECT.name} logo`} className="site-header__logo" />
      </Link>

      <nav className="site-header__nav">
        <NavLink to={ROUTES.home} end className="site-header__link text-label">
          Home
        </NavLink>
        <button
          type="button"
          className="site-header__link text-label"
          onClick={() => document.getElementById('sky-globe')?.scrollIntoView({ behavior: 'smooth' })}
        >
          Sky Map
        </button>
        <NavLink to={ROUTES.dashboard} className="site-header__link text-label">
          Dashboard
        </NavLink>
      </nav>
    </header>
  );
}
