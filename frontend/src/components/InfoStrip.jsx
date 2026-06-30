import { Cpu, Globe, Mic2, Zap, BookOpen, Sliders, AlertTriangle, Lightbulb } from 'lucide-react';

const LANGS = [
  '🇬🇧 English','🇮🇳 Hindi','🇫🇷 French','🇩🇪 German',
  '🇪🇸 Spanish','🇮🇹 Italian','🇧🇷 Portuguese','🇷🇺 Russian',
  '🇯🇵 Japanese','🇰🇷 Korean','🇨🇳 Chinese','🇸🇦 Arabic',
];

function ParamCard({ color, name, range, description, tips }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.03)',
      border: '1px solid rgba(255,255,255,0.07)',
      borderRadius: 10,
      padding: '12px 14px',
      marginBottom: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{
          background: color + '22',
          color: color,
          fontWeight: 800,
          fontSize: '0.75rem',
          padding: '2px 10px',
          borderRadius: 100,
          border: `1px solid ${color}44`,
          letterSpacing: '0.04em',
        }}>{name}</span>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>{range}</span>
      </div>
      <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 6 }}>{description}</p>
      {tips.map((tip, i) => (
        <div key={i} style={{ display: 'flex', gap: 7, alignItems: 'flex-start', marginBottom: 4 }}>
          <span style={{ color: color, fontSize: '0.7rem', marginTop: 2, flexShrink: 0 }}>→</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>{tip}</span>
        </div>
      ))}
    </div>
  );
}

export default function InfoStrip() {
  return (
    <div style={{ marginTop: 24 }}>

      {/* Voice Cloning Explanation — full width banner */}
      <div style={{
        background: 'rgba(14, 18, 32, 0.85)',
        backdropFilter: 'blur(20px)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 18,
        padding: '28px 32px',
        marginBottom: 20,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <div style={{ width: 32, height: 32, background: 'rgba(139, 92, 246, 0.15)', border: '1px solid rgba(139,92,246,0.3)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#a78bfa' }}>
            <Sliders size={16} />
          </div>
          <div>
            <div style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-main)' }}>Voice Cloning Controls — Explained</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Understanding the expressiveness parameters will help you get the best output</div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
          <ParamCard
            color="#a78bfa"
            name="Exaggeration"
            range="0.0 → 1.0 · default: 0.5"
            description="Controls how dramatically expressive and emotional the voice sounds. This is the 'performance intensity' dial — it makes the voice more theatrical and varied in pitch, pace, and energy."
            tips={[
              'Low (0.1–0.3): Calm, flat, monotone — great for audiobooks, news narration, or corporate voiceovers.',
              'Mid (0.4–0.6): Natural, balanced expressiveness — best for most use cases.',
              'High (0.7–1.0): Highly energetic and dramatic — great for storytelling, ads, or entertainment content. May sound over-the-top.',
            ]}
          />

          <ParamCard
            color="#818cf8"
            name="CFG Weight"
            range="0.0 → 1.0 · default: 0.5"
            description='Short for "Classifier-Free Guidance Weight". This controls how strictly the model sticks to the reference voice sample vs. using its own creative interpretation. Higher = closer to the original voice.'
            tips={[
              'Low (0.1–0.3): Model takes more creative freedom — voice may drift from the reference but sound more natural.',
              'Mid (0.4–0.6): Good balance between faithfulness to the reference voice and natural flow.',
              'High (0.7–1.0): Closely mimics the reference audio — best when the source clip is clean and high quality.',
            ]}
          />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {/* Best practices */}
            <div style={{
              background: 'rgba(16, 185, 129, 0.07)',
              border: '1px solid rgba(16, 185, 129, 0.2)',
              borderRadius: 10,
              padding: '14px 16px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8, color: '#6ee7b7', fontSize: '0.78rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                <Lightbulb size={13} /> Tips for Best Results
              </div>
              <div className="feature-list">
                {[
                  'Use a clean reference audio clip with no background noise (5–30 sec ideal).',
                  'Higher quality reference = better cloning accuracy regardless of settings.',
                  'Start with defaults (0.5 / 0.5) and adjust one slider at a time.',
                  'For storytelling: raise Exaggeration to ~0.7, keep CFG Weight ~0.5.',
                  'For professional narration: lower Exaggeration to ~0.3, raise CFG to ~0.7.',
                ].map((t, i) => (
                  <li key={i} style={{ marginBottom: 5 }}>
                    <span className="feature-dot" style={{ background: '#10b981' }} />
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{t}</span>
                  </li>
                ))}
              </div>
            </div>

            {/* Gotchas */}
            <div style={{
              background: 'rgba(245, 158, 11, 0.06)',
              border: '1px solid rgba(245, 158, 11, 0.18)',
              borderRadius: 10,
              padding: '14px 16px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8, color: '#fbbf24', fontSize: '0.78rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                <AlertTriangle size={13} /> Watch Out For
              </div>
              <div className="feature-list">
                {[
                  'First run downloads model weights (~500MB) — may take 2+ minutes silently.',
                  'Very high exaggeration on short texts can cause artifacts or stuttering.',
                  'The model only generates in English regardless of input language (translation happens automatically).',
                ].map((t, i) => (
                  <li key={i} style={{ marginBottom: 5 }}>
                    <span className="feature-dot" style={{ background: '#f59e0b' }} />
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{t}</span>
                  </li>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom 4-tile strip */}
      <div className="info-strip">
        {/* Languages */}
        <div className="info-tile">
          <div className="info-tile__label">
            <Globe size={12} style={{ display: 'inline', marginRight: 5 }} />
            Supported Languages
          </div>
          <div className="lang-chips">
            {LANGS.map(l => <span key={l} className="lang-chip">{l}</span>)}
          </div>
        </div>

        {/* Voice Engine */}
        <div className="info-tile">
          <div className="info-tile__label">
            <Mic2 size={12} style={{ display: 'inline', marginRight: 5 }} />
            Voice Engine
          </div>
          <ul className="feature-list">
            <li><span className="feature-dot" style={{ background: '#818cf8' }} />13 Kokoro preset voices (English, multilingual)</li>
            <li><span className="feature-dot" style={{ background: '#a78bfa' }} />Zero-shot voice cloning via Chatterbox TTS</li>
            <li><span className="feature-dot" style={{ background: '#6ee7b7' }} />Exaggeration + CFG Weight expressiveness controls</li>
            <li><span className="feature-dot" style={{ background: '#94a3b8' }} />Upload .SRT or .TXT script to auto-dub</li>
          </ul>
        </div>

        {/* System specs */}
        <div className="info-tile">
          <div className="info-tile__label">
            <Cpu size={12} style={{ display: 'inline', marginRight: 5 }} />
            System Specs
          </div>
          <ul className="feature-list">
            <li><span className="feature-dot" />Max video size: <strong style={{ color: '#f1f5f9' }}>100 MB</strong></li>
            <li><span className="feature-dot" />Voice clone text: <strong style={{ color: '#f1f5f9' }}>1,500 chars</strong></li>
            <li><span className="feature-dot" />ASR: Faster-Whisper (CPU · int8)</li>
            <li><span className="feature-dot" />Enhancement: Gemma-3 12B (OpenRouter)</li>
          </ul>
        </div>

        {/* How to use */}
        <div className="info-tile">
          <div className="info-tile__label">
            <BookOpen size={12} style={{ display: 'inline', marginRight: 5 }} />
            Quick Start
          </div>
          <ul className="feature-list">
            <li><span className="feature-dot" style={{ background: '#818cf8' }} /><strong style={{ color: '#a5b4fc' }}>Step 1</strong> — Upload video or paste YouTube URL</li>
            <li><span className="feature-dot" style={{ background: '#a78bfa' }} /><strong style={{ color: '#c4b5fd' }}>Step 2</strong> — AI transcribes and enhances subtitles</li>
            <li><span className="feature-dot" style={{ background: '#6ee7b7' }} /><strong style={{ color: '#6ee7b7' }}>Step 3</strong> — Download SRT/VTT or burn into video</li>
            <li><span className="feature-dot" style={{ background: '#fbbf24' }} /><strong style={{ color: '#fbbf24' }}>Step 4</strong> — Use script for AI voice dubbing</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
