import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

// Isolated document keeps every existing archive handler and CSS selector intact.
export default function AdvancedView() {
  const frame = useRef(null);
  const location = useLocation();
  const expectedSearch = useRef(location.search);
  const ignoreMessagesUntilLoad = useRef(false);
  const navigate = useNavigate();
  const initialSrc = useRef('/legacy.html' + location.search);
  useEffect(() => {
    const receive = event => {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow || event.data?.type !== 'archive-state') return;
      const query = new URLSearchParams(event.data.search);
      // Ignore a state message emitted by the old iframe while it is being
      // replaced after a parent Settings change. Without this guard, the old
      // smooth=true state could immediately overwrite smooth=false.
      if (ignoreMessagesUntilLoad.current) return;
      expectedSearch.current = event.data.search;
      navigate({ pathname: location.pathname, search: '?' + query }, { replace: true });
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [navigate, location.pathname]);
  useEffect(() => {
    expectedSearch.current = location.search;
    if (frame.current && frame.current.contentWindow?.location.search !== location.search) {
      ignoreMessagesUntilLoad.current = true;
      frame.current.src = '/legacy.html' + location.search;
    }
  }, [location.search]);
  useEffect(() => {
    const element = frame.current;
    let observer;
    const resize = () => {
      observer?.disconnect();
      const doc = element.contentDocument;
      if (!doc?.body) return;
      const update = () => { element.style.height = `${Math.ceil((doc.querySelector('.app') || doc.body).getBoundingClientRect().height) + 32}px`; };
      observer = new ResizeObserver(update);
      observer.observe(doc.body);
      update();
    };
    const onLoad = () => { ignoreMessagesUntilLoad.current = false; resize(); };
    element.addEventListener('load', onLoad);
    resize();
    return () => { element.removeEventListener('load', onLoad); observer?.disconnect(); };
  }, []);
  return <section className="advanced-mode" aria-label="SPHEREx sky viewer">
    <iframe ref={frame} src={initialSrc.current} title="SPHEREx sky viewer — NASA/IPAC IRSA data" className="advanced-mode__frame" />
  </section>;
}
