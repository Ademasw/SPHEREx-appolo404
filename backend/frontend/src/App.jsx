/**
 * src/App.jsx — root component.
 *
 * Renders the global animated black/purple gradient ONCE (it stays mounted
 * behind every page, so it never "restarts" on navigation), and the router
 * on top of it.
 */
import AnimatedBackground from './components/background/AnimatedBackground.jsx';
import AppRouter from './router/AppRouter.jsx';

export default function App() {
  return (
    <>
      <AnimatedBackground />
      <AppRouter />
    </>
  );
}

