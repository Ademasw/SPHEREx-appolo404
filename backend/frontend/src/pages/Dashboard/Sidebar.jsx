/**
 * Sidebar — Logo, target input and view-mode switcher.
 */
import { Link, NavLink, useLocation } from 'react-router-dom';
import { ASSETS } from '../../assets';
import { PROJECT } from '../../config/project';
import { ROUTES } from '../../router/routes';

const VIEW_MODES = [
  { to: ROUTES.advanced, label: 'Explore', hint: 'Archive and visit stacks' },
  { to: ROUTES.player, label: 'Player', hint: 'Animated sequence' },
  { to: ROUTES.compare, label: 'Compare', hint: 'Side-by-side epochs' },
  { to: ROUTES.colour, label: 'Colour', hint: 'Six-detector composite' },
];

export default function Sidebar({
  coordinates,
  onCoordinatesSubmit,
}) {
  const location = useLocation();
  const isAdvanced = location.pathname.endsWith('/advanced');

  return (
    <aside className="sidebar">
      {/* --- Brand: large standalone logo on a soft lilac backdrop --- */}
      <Link to={ROUTES.home} className="sidebar__brand" aria-label={`${PROJECT.name} — home`}>
        <img src={ASSETS.logo} alt={`${PROJECT.name} logo`} className="sidebar__logo" />
      </Link>

      <form className="sidebar__section" onSubmit={event => {
        event.preventDefault();
        onCoordinatesSubmit(new FormData(event.currentTarget).get('q').trim());
      }}>
        <label htmlFor="sidebar-target">Object or RA / Dec</label>
        <input id="sidebar-target" name="q" key={coordinates} defaultValue={coordinates} required className="field__control" />
        <button type="submit" className="btn-primary">Show observations</button>
      </form>
      {/* --- View-mode switcher --- */}
      <div className="sidebar__section">
        <p className="sidebar__heading text-label text-muted">View mode</p>
        <div className="sidebar__switcher" role="tablist">
          {VIEW_MODES.map((mode) => (
            <NavLink key={mode.to} to={{ pathname: mode.to, search: (() => { const next = new URLSearchParams(location.search); if (mode.to === ROUTES.colour) next.set('det', 'all'); return `?${next}`; })() }} role="tab" className="sidebar__mode">
              <span className="text-small">{mode.label}</span>
              <span className="text-caption text-muted">{mode.hint}</span>
            </NavLink>
          ))}
        </div>
      </div>

      {isAdvanced && <div id="advanced-controls" className="sidebar__archive-controls" />}
      <Link to={ROUTES.home} className="sidebar__back text-label text-muted">
        ← Back to landing
      </Link>
    </aside>
  );
}
