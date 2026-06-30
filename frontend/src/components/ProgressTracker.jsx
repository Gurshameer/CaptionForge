import { useEffect, useState } from 'react';
import { apiUrl } from '../api';
import { Music, Languages, Sparkles, FileText, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';

const STEPS = [
  { id: 'audio_extraction',      label: 'Audio Extraction',      sub: 'Extracting audio track', icon: Music },
  { id: 'speech_recognition',    label: 'Speech Recognition',    sub: 'Whisper transcribing...', icon: Languages },
  { id: 'transcript_enhancement',label: 'AI Enhancement',        sub: 'Gemma polishing transcript', icon: Sparkles },
  { id: 'subtitle_generation',   label: 'Subtitle Generation',   sub: 'Formatting & timing', icon: FileText },
];

export default function ProgressTracker({ taskId, onComplete, onFailure, onReset }) {
  const [data, setData] = useState({ status: 'PENDING', progress: 0, current_step: '', detected_language: null, error: null });

  useEffect(() => {
    if (!taskId) return;
    let id = null;

    const poll = async () => {
      try {
        const res = await fetch(apiUrl(`/api/v1/subtitles/status/${taskId}`));
        if (!res.ok) return;
        const d = await res.json();
        setData(d);
        if (d.status === 'COMPLETED') { clearInterval(id); onComplete?.(d); }
        else if (d.status === 'FAILED') { clearInterval(id); onFailure?.(d.error || 'Failed'); }
      } catch {}
    };

    poll();
    id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, [taskId, onComplete, onFailure]);

  const { status, progress, current_step, detected_language, error } = data;

  const getStatus = (stepId) => {
    if (status === 'FAILED') return 'failed';
    if (status === 'COMPLETED') return 'completed';
    const cur = STEPS.findIndex(s => s.id === current_step);
    const idx = STEPS.findIndex(s => s.id === stepId);
    if (cur === -1) return 'pending';
    if (idx < cur) return 'completed';
    if (idx === cur) return 'active';
    return 'pending';
  };

  return (
    <div className="progress-card animate-up" style={{ background: 'rgba(99, 102, 241, 0.07)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 12, padding: 16, marginTop: 4 }}>
      <div className="progress-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className={`status-pill ${status.toLowerCase()}`}>
            {status === 'PROCESSING' && <Loader2 size={10} className="spinner" />}
            {status === 'COMPLETED' && <CheckCircle2 size={10} />}
            {status === 'FAILED' && <AlertCircle size={10} />}
            {status === 'PENDING' ? 'Queued' : status}
          </span>
          {detected_language && (
            <span className="lang-chip" style={{ fontSize: '0.7rem' }}>{detected_language.toUpperCase()}</span>
          )}
        </div>
        <span className="progress-pct">{Math.round(progress)}%</span>
      </div>

      {status === 'PROCESSING' && (
        <div className="voice-warning" style={{ marginTop: 14, marginBottom: 4 }}>
          <AlertCircle size={14} style={{ flexShrink: 0 }} />
          <span>Please don't click any buttons or refresh the page, or you may lose your output.</span>
        </div>
      )}

      <div className="progress-track">
        <div className={`progress-fill ${status === 'FAILED' ? 'failed' : ''}`} style={{ width: `${progress}%` }} />
      </div>

      <div className="pipeline-steps">
        {STEPS.map(step => {
          const s = getStatus(step.id);
          const Icon = step.icon;
          return (
            <div key={step.id} className={`step-row ${s}`}>
              <div className="step-dot">
                {s === 'completed' ? <CheckCircle2 size={14} /> : s === 'active' ? <Loader2 size={14} className="spinner" /> : <Icon size={14} />}
              </div>
              <div className="step-info">
                <div className="step-name">{step.label}</div>
                <div className="step-meta">
                  {s === 'active' && step.sub}
                  {s === 'completed' && 'Done ✓'}
                  {s === 'pending' && 'Waiting...'}
                  {s === 'failed' && 'Error'}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {status === 'FAILED' && (
        <div className="error-block">
          <AlertCircle size={16} className="error-block__icon" />
          <div>
            <div className="error-block__title">Generation Failed</div>
            <div className="error-block__msg">{error || 'An unexpected error occurred.'}</div>
          </div>
          {onReset && (
            <button onClick={onReset} className="btn btn-danger btn-sm" style={{ marginLeft: 'auto', flexShrink: 0 }}>
              Try Again
            </button>
          )}
        </div>
      )}
    </div>
  );
}
