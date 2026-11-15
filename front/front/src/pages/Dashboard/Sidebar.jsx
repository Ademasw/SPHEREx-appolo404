/**
 * Sidebar — Logo (on lilac backdrop), functional menu (`Overview`, `Filter`,
 * `Settings`), "Coordinates" input and view-mode switcher.
 *
 * - MENU_ITEMS open/toggle interactive workspace panels in DashboardPanel.
 * - VIEW_MODES switch between the Player and Side-by-Side routes.
 */
import { useEffect, useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { ASSETS } from '../../assets';
import { PROJECT } from '../../config/project';
import { ROUTES } from '../../router/routes';

const MENU_ITEMS = [
  { id: 'overview', label: 'Overview', hint: 'Metadata & details' },
  { id: 'filter', label: 'Filter', hint: 'Zodi subtraction' },
  { id: 'settings', label: 'Settings', hint: 'Compare & inputs' },
];

const VIEW_MODES = [
  { to: ROUTES.player, label: 'Player', hint: 'Animated sequence' },
  { to: ROUTES.compare, label: 'Compare', hint: 'Side-by-side epochs' },
];

export default function Sidebar({
  coordinates,
  onCoordinatesSubmit,
  activeMenu,
  onSelectMenu,
  zodiEnabled,
}) {
  const [draft, setDraft] = useState(coordinates);

  // Keep input synced when a quick target preset is picked in Settings.
  useEffect(() => {
    setDraft(coordinates);
  }, [coordinates]);

  const handleSubmit = (e) => {
    e.preventDefault();
    onCoordinatesSubmit(draft.trim());
  };

  return (
    <aside className="sidebar">
      {/* --- Brand: large standalone logo on a soft lilac backdrop --- */}
      <Link to={ROUTES.home} className="sidebar__brand" aria-label={`${PROJECT.name} — home`}>
        <img src={ASSETS.logo} alt={`${PROJECT.name} logo`} className="sidebar__logo" />
      </Link>

      {/* --- Functional workspace menu --- */}
      <nav className="sidebar__section" aria-label="Dashboard tools">
        <p className="sidebar__heading text-label text-muted">Menu</p>
        <ul className="sidebar__menu">
          {MENU_ITEMS.map((item) => {
            const isActive = activeMenu === item.id;
            const isFilterOff = item.id === 'filter' && !zodiEnabled;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  aria-pressed={isActive}
                  className={`sidebar__menu-item${isActive ? ' is-active' : ''}${isFilterOff ? ' is-filter-off' : ''}`}
                  onClick={() => onSelectMenu(isActive ? null : item.id)}
                >
                  <span
                    className={`sidebar__dot${isFilterOff ? ' sidebar__dot--off' : ''}`}
                    aria-hidden="true"
                  />
                  <span className="sidebar__menu-copy">
                    <span className="text-small">{item.label}</span>
                    <span className="text-caption text-muted">
                      {item.id === 'filter'
                        ? `Zodi subtraction · ${zodiEnabled ? 'ON' : 'OFF'}`
                        : item.hint}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* --- Coordinates input --- */}
      <form className="sidebar__section" onSubmit={handleSubmit}>
        <label htmlFor="coords" className="sidebar__heading text-label text-muted">
          Coordinates
        </label>
        <div className="sidebar__input-row">
          <input
            id="coords"
            type="text"
            className="sidebar__input text-mono"
            placeholder="RA, Dec  e.g. 83.82, -5.39"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoComplete="off"
          />
          <button type="submit" className="sidebar__go text-label" aria-label="Locate coordinates">
            Go
          </button>
        </div>
      </form>

      {/* --- View-mode switcher --- */}
      <div className="sidebar__section">
        <p className="sidebar__heading text-label text-muted">View mode</p>
        <div className="sidebar__switcher" role="tablist">
          {VIEW_MODES.map((mode) => (
            <NavLink key={mode.to} to={mode.to} role="tab" className="sidebar__mode">
              <span className="text-small">{mode.label}</span>
              <span className="text-caption text-muted">{mode.hint}</span>
            </NavLink>
          ))}
        </div>
      </div>

      <Link to={ROUTES.home} className="sidebar__back text-label text-muted">
        ← Back to landing
      </Link>
    </aside>
  );
}
