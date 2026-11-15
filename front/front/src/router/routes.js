/**
 * src/router/routes.js — route path constants.
 * Kept separate from AppRouter.jsx to avoid circular imports
 * (pages import these paths, and AppRouter imports the pages).
 */
export const ROUTES = {
  home: '/',
  dashboard: '/dashboard',
  player: '/dashboard/player', // Page 2 — View Mode A
  compare: '/dashboard/compare', // Page 3 — View Mode B
};

