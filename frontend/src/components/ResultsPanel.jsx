import { useState, useEffect } from 'react';
import { Download, Copy, Check, FileCode2, AlertCircle, Loader2, Flame, Play, Video, RefreshCw } from 'lucide-react';
import { apiUrl } from '../api';

function stripSrt(content) {
  if (!content) return '';
  return content.split('\n')
    .filter(l => !/^\d+$/.test(l.trim()))
    .filter(l => !/-->/.test(l))
    .filter(l => l.trim() !== '')
    .join(' ');
}

function highlightSrt(content) {
  return content
    .replace(/^(\d+)$/gm, '<span class="idx">$1</span>')
    .replace(/(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})/g, '<span class="ts">$1</span>');
}

export default function ResultsPanel({ taskId, downloadUrl, detectedLanguage, onSrtLoaded, onUseForVoice, onReset }) {
  const [srt, setSrt] = useState('');
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [burning, setBurning] = useState(false);
  const [burnUrl, setBurnUrl] = useState(null);
  const [burnError, setBurnError] = useState(null);

  useEffect(() => {
    if (!downloadUrl) return;
    setLoading(true);
    fetch(apiUrl(downloadUrl))
      .then(r => { if (!r.ok) throw new Error('Failed'); return r.text(); })
      .then(text => { setSrt(text); onSrtLoaded?.(stripSrt(text)); setFetchError(null); })
      .catch(() => setFetchError('Could not load preview.'))
      .finally(() => setLoading(false));
  }, [downloadUrl]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(srt).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleBurn = async () => {
    setBurning(true);
    setBurnError(null);
    try {
      const res = await fetch(apiUrl(`/api/v1/subtitles/burn/${taskId}`), { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Burn failed');
      setBurnUrl(data.download_url);
    } catch (e) {
      setBurnError(e.message);
    } finally {
      setBurning(false);
    }
  };

  return (
    <div className="card card--active animate-up">
      <div className="card-header">
        <div className="card-icon card-icon--green">
          <FileCode2 size={16} />
        </div>
        <div style={{ flex: 1 }}>
          <div className="card-title">Subtitles Ready</div>
          <div className="card-subtitle">
            {detectedLanguage && <>Detected: <strong style={{ color: '#f1f5f9' }}>{detectedLanguage.toUpperCase()}</strong> · </>}
            Export, burn-in, or use for voice dubbing
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="result-actions">
        <button onClick={handleCopy} className={`btn btn-ghost btn-icon ${copied ? 'btn-success' : ''}`} disabled={!srt} title="Copy SRT">
          {copied ? <Check size={15} /> : <Copy size={15} />}
        </button>
        <a href={apiUrl(downloadUrl)} download className="btn btn-ghost btn-sm">
          <Download size={14} /> .SRT
        </a>
        <a href={apiUrl(`/api/v1/subtitles/download-vtt/${taskId}`)} download className="btn btn-ghost btn-sm">
          <Download size={14} /> .VTT
        </a>
        <button
          onClick={handleBurn}
          className="btn btn-ghost btn-sm"
          style={{ borderColor: burnUrl ? 'var(--green-glow)' : undefined, color: burnUrl ? '#6ee7b7' : undefined }}
          disabled={burning || !!burnUrl || !srt}
        >
          {burning ? <><Loader2 size={14} className="spinner" /> Burning...</> : <><Flame size={14} /> Burn-in</>}
        </button>
      </div>

      {/* SRT Preview */}
      <div className="subtitle-preview">
        {loading ? (
          <div className="preview-empty">
            <Loader2 size={24} className="spinner" style={{ color: 'var(--indigo)' }} />
            <span style={{ fontSize: '0.8rem' }}>Loading preview...</span>
          </div>
        ) : fetchError ? (
          <div className="preview-empty">
            <AlertCircle size={20} style={{ color: 'var(--red)' }} />
            <span style={{ fontSize: '0.8rem', color: '#fca5a5' }}>{fetchError}</span>
          </div>
        ) : (
          <pre dangerouslySetInnerHTML={{ __html: highlightSrt(srt) }} />
        )}
      </div>

      {burnError && (
        <div className="error-block" style={{ marginTop: 12 }}>
          <AlertCircle size={14} className="error-block__icon" />
          <div className="error-block__msg">{burnError}</div>
        </div>
      )}

      {/* Burned video */}
      {burnUrl && (
        <div className="burn-result">
          <div className="burn-result-header">
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.875rem', fontWeight: 600 }}>
              <Video size={16} style={{ color: '#6ee7b7' }} /> Subtitled Video
            </span>
            <a href={apiUrl(burnUrl)} download className="btn btn-ghost btn-sm">
              <Download size={14} /> Download
            </a>
          </div>
          <div className="video-wrapper">
            <video controls src={apiUrl(burnUrl)} />
          </div>
        </div>
      )}

      {/* Footer actions */}
      <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
        <button
          className="btn btn-primary"
          style={{ flex: 1 }}
          onClick={() => onUseForVoice?.(stripSrt(srt))}
          disabled={!srt}
        >
          <Play size={15} /> Use for Voice Dubbing
        </button>
        <button onClick={onReset} className="btn btn-ghost" title="New video">
          <RefreshCw size={15} />
        </button>
      </div>
    </div>
  );
}
