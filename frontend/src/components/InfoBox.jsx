import { Info } from 'lucide-react';

export default function InfoBox() {
  const languages = ['EN', 'RU', 'JA', 'DE', 'FR'];
  
  return (
    <div className="card info-section">
      <div className="card__title">
        <Info size={18} className="card__title-icon" />
        Instructions & Features
      </div>

      <div>
        <h4>Supported Languages</h4>
        <div className="lang-badges">
          {languages.map(lang => (
            <span key={lang} className="lang-badge">{lang}</span>
          ))}
        </div>
      </div>

      <div style={{ marginTop: 'var(--space-md)' }}>
        <h4>Upload Constraints</h4>
        <div>
          <span className="constraint-pill">
            Max Size: 100 MB
          </span>
        </div>
      </div>
    </div>
  );
}
