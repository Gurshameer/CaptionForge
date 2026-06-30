import { Info, Zap, Settings2, Sparkles, Wand2 } from 'lucide-react';

const LANGUAGES = [
  { code: 'English', flag: '🇬🇧' },
  { code: 'Hindi', flag: '🇮🇳' },
  { code: 'French', flag: '🇫🇷' },
  { code: 'German', flag: '🇩🇪' },
  { code: 'Spanish', flag: '🇪🇸' },
  { code: 'Italian', flag: '🇮🇹' },
  { code: 'Portuguese', flag: '🇧🇷' },
  { code: 'Russian', flag: '🇷🇺' },
  { code: 'Japanese', flag: '🇯🇵' },
  { code: 'Korean', flag: '🇰🇷' },
  { code: 'Chinese', flag: '🇨🇳' },
  { code: 'Arabic', flag: '🇸🇦' },
];

export default function InfoBox() {
  return (
    <div className="card info-section">
      <div className="card__title">
        <Sparkles size={18} className="card__title-icon" />
        Capabilities &amp; Limits
      </div>

      <div>
        <h4>Supported Languages</h4>
        <div className="lang-badges">
          {LANGUAGES.map(lang => (
            <span key={lang.code} className="lang-badge">
              {lang.flag} {lang.code}
            </span>
          ))}
        </div>
      </div>

      <div style={{ marginTop: 'var(--space-lg)' }}>
        <h4>System Limits</h4>
        <div>
          <span className="constraint-pill">
            <Zap size={14} style={{marginRight: 6, color: 'var(--accent)'}}/> Max Size: 100 MB
          </span>
          <span className="constraint-pill">
            <Settings2 size={14} style={{marginRight: 6, color: 'var(--primary)'}}/> Voice Clone: 1500 chars
          </span>
        </div>
      </div>

      <div style={{ marginTop: 'var(--space-lg)' }}>
        <h4>Voice Engine Features</h4>
        <ul className="steps-list">
          <li><Wand2 size={16} color="var(--primary)"/> 13 preset premium AI voices via Kokoro</li>
          <li><Wand2 size={16} color="var(--accent)"/> Zero-shot voice cloning via Chatterbox TTS</li>
          <li><Wand2 size={16} color="var(--success)"/> Upload custom SRT to generate voice dubs</li>
        </ul>
      </div>
    </div>
  );
}
