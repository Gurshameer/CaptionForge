import { Subtitles } from 'lucide-react';

export default function Header() {
  return (
    <header>
      <h1 className="app-title">
        <Subtitles size={40} style={{ verticalAlign: 'middle', marginRight: '12px', color: 'var(--primary)' }} />
        Caption<span>Forge</span>
      </h1>
      <p className="tagline">
        AI-powered subtitle generation. Upload a video, get perfectly timed subtitles in seconds.
      </p>
    </header>
  );
}
