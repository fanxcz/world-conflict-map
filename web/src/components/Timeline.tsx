import { useEffect, useRef, useState } from 'react';

export default function Timeline({ date, setDate }: { date: string; setDate: (d: string) => void }) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (playing) {
      timer.current = window.setInterval(() => {
        setDate(shift(dateRef.current, 1));
      }, Math.max(150, 1000 / speed));
    } else if (timer.current) window.clearInterval(timer.current);
    return () => { if (timer.current) window.clearInterval(timer.current); };
  }, [playing, speed]);

  const dateRef = useRef(date);
  dateRef.current = date;

  function shift(d: string, days: number): string {
    const base = d ? new Date(d) : new Date('2026-09-30');
    base.setDate(base.getDate() + days);
    return base.toISOString().slice(0, 10);
  }

  return (
    <div className="timelinebar">
      <strong>Timeline</strong>
      <button onClick={() => setPlaying(!playing)}>{playing ? 'Pause' : 'Play'}</button>
      <button onClick={() => setDate(shift(date, -1))}>◀ Prev</button>
      <button onClick={() => setDate(shift(date, 1))}>Next ▶</button>
      <input type="date" style={{ width: 150 }} value={date} onChange={(e) => setDate(e.target.value)} />
      <input type="range" min={Date.parse('2024-01-01')} max={Date.parse('2026-12-31')} step={86400000}
        value={date ? Date.parse(date) : Date.parse('2026-09-30')}
        onChange={(e) => setDate(new Date(Number(e.target.value)).toISOString().slice(0, 10))}
        style={{ flex: 1, minWidth: 120 }} />
      <span>Speed:</span>
      {[0.5, 1, 2, 5].map((s) => (
        <button key={s} onClick={() => setSpeed(s)} className={speed === s ? 'primary' : ''}>{s}x</button>
      ))}
      <span style={{ color: '#9aa6b8' }}>{date || 'latest'}</span>
    </div>
  );
}

export function shiftDate(d: string, days: number): string {
  const base = d ? new Date(d) : new Date();
  base.setDate(base.getDate() + days);
  return base.toISOString().slice(0, 10);
}
