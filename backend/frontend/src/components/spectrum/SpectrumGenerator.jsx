import { useEffect, useState } from 'react';
import SpectrumView from './SpectrumView.jsx';

const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
export default function SpectrumGenerator({query, name}) {
  const search = new URLSearchParams(query).toString();
  const [running,setRunning] = useState(false);
  const [data,setData] = useState(null);
  const [error,setError] = useState('');
  useEffect(() => {setRunning(false);setData(null);setError('');},[search]);
  useEffect(() => {
    if (!running) return;
    const controller=new AbortController(); let timer;
    const deadline=Date.now()+30*60*1000;
    const poll=async()=>{
      try {
        const response=await fetch(`${base}/api/spectrum?${search}`,{signal:controller.signal});
        const result=await response.json();
        if(!response.ok)throw new Error(result.detail || 'Spectrum service unavailable');
        if(controller.signal.aborted)return;
        setData(result);
        if(result.status==='running') {
          if(Date.now()>deadline)throw new Error('Processing time limit reached. Generate again to resume cached detectors.');
          timer=setTimeout(poll,2000);
        } else setRunning(false);
      } catch(error){if(error.name!=='AbortError'){setError(error.message);setRunning(false);}}
    };
    poll();return()=>{controller.abort();clearTimeout(timer);};
  },[running,search]);
  const download=()=>{
    const link=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
    link.href=url;link.download='spherex-spectrum.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  return <section aria-label="Generate six-detector spectrum">
    <p>Generate the spectrum at the requested sky position across D1–D6. Measurements appear as detectors finish; colours distinguish epochs.</p>
    <button disabled={running || !query.q} onClick={()=>{setError('');setRunning(true);}}>Generate spectrum</button>
    {running && <button onClick={()=>setRunning(false)}>Stop waiting</button>}
    {data && <button onClick={download}>Export current spectrum JSON</button>}
    {error && <p role="alert">{error}</p>}
    {Object.entries(data?.errors || {}).map(([det,message])=><p role="alert" key={det}>{det}: {message}</p>)}
    {(running || data) && <SpectrumView spectrum={data} name={name}/>}
  </section>;
}
