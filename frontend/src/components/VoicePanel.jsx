import { useState, useEffect, useRef } from 'react';
import { Mic, Download, AlertCircle, Loader2, Volume2, FileText, CheckCircle2, BrainCog, AudioLines, Settings2, Languages, RefreshCw } from 'lucide-react';
import { apiUrl } from '../api';

const MAX_CHARS = 1500;
const ALLOWED_AUDIO = ['.wav', '.mp3', '.ogg', '.flac', '.m4a', '.aac'];
const MAX_AUDIO_MB = 10;
const MAX_AUDIO_BYTES = MAX_AUDIO_MB * 1024 * 1024;

const VOICE_STEPS = [
  { id: 'loading_model',    label: 'Loading Model',    icon: Settings2 },
  { id: 'processing_text', label: 'Processing Text',  icon: BrainCog },
  { id: 'translating',     label: 'Translating',       icon: Languages },
  { id: 'synthesizing',    label: 'Synthesizing',      icon: AudioLines },
  { id: 'saving',          label: 'Saving',             icon: FileText },
];

function simStep(sec, isClone) {
  if (sec < 3) return 'loading_model';
  if (sec < (isClone ? 30 : 8)) return 'processing_text';
  if (sec < (isClone ? 40 : 12)) return 'translating';
  if (sec < (isClone ? 90 : 20)) return 'synthesizing';
  return 'saving';
}

export default function VoicePanel({ voiceInput, defaultLanguage }) {
  const [voices, setVoices] = useState({});
  const [selectedVoice, setSelectedVoice] = useState('');
  const [text, setText] = useState('');
  const [refFile, setRefFile] = useState(null);
  const [exaggeration, setExaggeration] = useState(0.5);
  const [cfgWeight, setCfgWeight] = useState(0.5);
  const [mode, setMode] = useState('preset');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [audioUrl, setAudioUrl] = useState(null);
  const [progress, setProgress] = useState(null);

  const refInputRef = useRef(null);
  const textInputRef = useRef(null);
  const startRef = useRef(null);
  const pollRef = useRef(null);
  const animRef = useRef(null);

  useEffect(() => {
    fetch(apiUrl('/api/v1/voice/voices'))
      .then(r => r.json())
      .then(d => {
        setVoices(d.voices || {});
        const keys = Object.keys(d.voices || {});
        const match = keys.find(k => d.voices[k].lang === defaultLanguage);
        setSelectedVoice(match || d.voices?.['af_heart'] ? 'af_heart' : keys[0] || '');
      })
      .catch(() => {});
  }, [defaultLanguage]);

  useEffect(() => {
    if (voiceInput?.text) setText(voiceInput.text);
  }, [voiceInput]);

  const startPoll = (id) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(apiUrl(`/api/v1/voice/status/${id}`));
        const d = await res.json();
        if (d.status === 'COMPLETED') {
          clearInterval(pollRef.current);
          clearInterval(animRef.current);
          setProgress(prev => ({ ...prev, step: 'done', pct: 100 }));
          setTimeout(() => { setAudioUrl(d.download_url); setLoading(false); setProgress(null); }, 600);
        } else if (d.status === 'FAILED') {
          clearInterval(pollRef.current);
          clearInterval(animRef.current);
          setProgress(prev => ({ ...prev, failed: true }));
          setError(d.error || 'Voice generation failed');
          setLoading(false);
        }
      } catch {
        clearInterval(pollRef.current);
        clearInterval(animRef.current);
        setError('Connection lost');
        setLoading(false);
        setProgress(null);
      }
    }, 2000);
  };

  const startAnim = (isClone) => {
    startRef.current = Date.now();
    setProgress({ step: 'loading_model', pct: 5, failed: false });
    if (animRef.current) clearInterval(animRef.current);
    animRef.current = setInterval(() => {
      const sec = (Date.now() - startRef.current) / 1000;
      const step = simStep(sec, isClone);
      const map = { loading_model: 10, processing_text: 35, translating: 50, synthesizing: 65, saving: 80 };
      setProgress(prev => ({ ...prev, step, pct: Math.min(map[step] ?? 5, isClone ? 90 : 85) }));
    }, 1500);
  };

  const handleGenerate = async () => {
    if (!text.trim()) { setError('Enter some text first.'); return; }
    setLoading(true);
    setError('');
    setAudioUrl(null);
    startAnim(mode === 'clone');

    const fd = new FormData();
    fd.append('text', text);
    fd.append('language', defaultLanguage || 'en');

    let endpoint = '/api/v1/voice/generate';
    if (mode === 'clone') {
      if (!refFile) { setError('Upload a reference audio file.'); setLoading(false); setProgress(null); return; }
      fd.append('reference_audio', refFile);
      fd.append('exaggeration', exaggeration.toString());
      fd.append('cfg_weight', cfgWeight.toString());
      endpoint = '/api/v1/voice/clone';
    } else {
      fd.append('voice_id', selectedVoice);
    }

    try {
      const res = await fetch(apiUrl(endpoint), { method: 'POST', body: fd });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || d.error || 'Failed');
      startPoll(d.task_id);
    } catch (e) {
      setError(e.message);
      setLoading(false);
      setProgress(null);
      clearInterval(animRef.current);
    }
  };

  const handleRefUpload = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const ext = '.' + f.name.split('.').pop().toLowerCase();
    if (!ALLOWED_AUDIO.includes(ext)) { setError(`Unsupported. Use: ${ALLOWED_AUDIO.join(', ')}`); return; }
    if (f.size > MAX_AUDIO_BYTES) { setError(`Too large. Max ${MAX_AUDIO_MB}MB`); return; }
    setRefFile(f);
    setError('');
  };

  const handleTextFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      let c = ev.target.result;
      if (f.name.endsWith('.srt')) {
        c = c.split('\n').filter(l => !/^\d+$/.test(l.trim())).filter(l => !/-->/.test(l)).filter(l => l.trim()).join(' ');
      }
      setText(mode === 'clone' && c.length > MAX_CHARS ? c.slice(0, MAX_CHARS) : c);
    };
    reader.readAsText(f);
  };

  return (
    <div className="card" style={{ height: '100%' }}>
      <div className="card-header">
        <div className="card-icon card-icon--violet">
          <Mic size={16} />
        </div>
        <div>
          <div className="card-title">AI Voice Studio</div>
          <div className="card-subtitle">Generate speech or clone any voice</div>
        </div>
      </div>

      {/* Mode tabs */}
      <div className="tab-bar">
        <button className={`tab-btn ${mode === 'preset' ? 'active' : ''}`} onClick={() => setMode('preset')} disabled={loading}>
          <Volume2 size={13} /> Preset Voice
        </button>
        <button className={`tab-btn ${mode === 'clone' ? 'active' : ''}`} onClick={() => setMode('clone')} disabled={loading}>
          <Mic size={13} /> Voice Clone
        </button>
      </div>

      {/* Clone warning */}
      {mode === 'clone' && (
        <div className="voice-warning">
          <AlertCircle size={14} style={{ flexShrink: 0 }} />
          <span>CPU processing — may take 1-2 minutes. Text limited to {MAX_CHARS} chars.</span>
        </div>
      )}

      {/* Reference audio */}
      {mode === 'clone' && (
        <div className="ref-drop" onClick={() => refInputRef.current?.click()}>
          {refFile
            ? <div className="ref-drop__selected">🎤 {refFile.name}</div>
            : <div className="ref-drop__text">Click to upload reference audio (WAV, MP3, OGG, FLAC, M4A, AAC)</div>
          }
          <input type="file" ref={refInputRef} style={{ display: 'none' }} accept={ALLOWED_AUDIO.join(',')} onChange={handleRefUpload} />
        </div>
      )}

      {/* Expressiveness sliders */}
      {mode === 'clone' && (
        <div style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)', borderRadius: 12, padding: '14px 16px', marginBottom: 14 }}>
          <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#818cf8', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 }}>Expressiveness Controls</div>
          <div className="slider-row">
            <div className="slider-group">
              <div className="slider-label">
                <span>Exaggeration</span>
                <span>{exaggeration.toFixed(2)}</span>
              </div>
              <input type="range" min="0" max="1" step="0.05" value={exaggeration} onChange={(e) => setExaggeration(parseFloat(e.target.value))} disabled={loading} />
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 3 }}>
                {exaggeration <= 0.3 ? '😐 Calm & flat' : exaggeration <= 0.6 ? '🙂 Natural & balanced' : '🎭 Dramatic & expressive'}
              </div>
            </div>
            <div className="slider-group">
              <div className="slider-label">
                <span>CFG Weight</span>
                <span style={{ color: '#818cf8' }}>{cfgWeight.toFixed(2)}</span>
              </div>
              <input type="range" min="0" max="1" step="0.05" value={cfgWeight} onChange={(e) => setCfgWeight(parseFloat(e.target.value))} disabled={loading} />
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 3 }}>
                {cfgWeight <= 0.3 ? '🎨 Creative (may drift)' : cfgWeight <= 0.6 ? '⚖️ Balanced fidelity' : '🔒 Strict voice match'}
              </div>
            </div>
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: 8, marginTop: 4 }}>
            💡 See <em>Voice Cloning Controls — Explained</em> below for detailed guidance.
          </div>
        </div>
      )}

      {/* Preset voice selector */}
      {mode === 'preset' && Object.keys(voices).length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <label className="field-label">Voice</label>
          <select value={selectedVoice} onChange={(e) => setSelectedVoice(e.target.value)} disabled={loading}>
            {Object.entries(voices).map(([id, v]) => (
              <option key={id} value={id}>{v.name} — {v.accent} ({v.gender})</option>
            ))}
          </select>
        </div>
      )}

      {/* Text input */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <label className="field-label" style={{ margin: 0 }}>Script</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => textInputRef.current?.click()}>
              <FileText size={12} /> Import File
            </button>
            <input type="file" ref={textInputRef} style={{ display: 'none' }} accept=".srt,.txt" onChange={handleTextFile} />
            {mode === 'clone' && (
              <span className={`char-counter ${text.length >= MAX_CHARS ? 'error' : text.length > MAX_CHARS * 0.85 ? 'warn' : ''}`}>
                {text.length}/{MAX_CHARS}
              </span>
            )}
          </div>
        </div>
        <textarea
          rows={5}
          value={text}
          onChange={(e) => {
            const v = e.target.value;
            setText(mode === 'clone' && v.length > MAX_CHARS ? v.slice(0, MAX_CHARS) : v);
          }}
          disabled={loading}
          placeholder="Type text here, or use 'Use for Voice Dubbing' from the subtitle panel..."
        />
      </div>

      {error && (
        <div style={{ marginBottom: 12, padding: '8px 12px', background: 'var(--red-soft)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 8, fontSize: '0.8rem', color: '#fca5a5' }}>
          ⚠ {error}
        </div>
      )}

      {/* Output: audio player OR progress OR generate button */}
      {audioUrl ? (
        <div className="audio-result">
          <audio src={apiUrl(audioUrl)} controls />
          <div style={{ display: 'flex', gap: 8 }}>
            <a href={apiUrl(audioUrl)} download className="btn btn-ghost btn-sm" style={{ flex: 1 }}>
              <Download size={14} /> Download Audio
            </a>
            <button className="btn btn-ghost btn-sm" onClick={() => setAudioUrl(null)}>
              <RefreshCw size={14} /> Again
            </button>
          </div>
        </div>
      ) : progress ? (
        <div style={{ background: 'rgba(99, 102, 241, 0.07)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 12, padding: 16, marginTop: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span className={`status-pill ${progress.failed ? 'failed' : 'processing'}`}>
              {progress.failed ? <><AlertCircle size={10} /> Failed</> : <><Loader2 size={10} className="spinner" /> Generating</>}
            </span>
            <span className="progress-pct" style={{ fontSize: '1.1rem' }}>{progress.pct ?? 0}%</span>
          </div>

          {!progress.failed && progress.step !== 'done' && (
            <div className="voice-warning" style={{ marginTop: 4, marginBottom: 14 }}>
              <AlertCircle size={14} style={{ flexShrink: 0 }} />
              <span>Please don't click any buttons or refresh the page, or you may lose your output.</span>
            </div>
          )}
          <div className="progress-track" style={{ marginBottom: 14 }}>
            <div className={`progress-fill ${progress.failed ? 'failed' : ''}`} style={{ width: `${progress.pct ?? 0}%` }} />
          </div>
          <div className="pipeline-steps">
            {VOICE_STEPS.map(step => {
              const ids = VOICE_STEPS.map(s => s.id);
              const cur = ids.indexOf(progress.step);
              const idx = ids.indexOf(step.id);
              const s = progress.failed ? 'failed' : progress.step === 'done' || idx < cur ? 'completed' : idx === cur ? 'active' : 'pending';
              const Icon = step.icon;
              return (
                <div key={step.id} className={`step-row ${s}`}>
                  <div className="step-dot">
                    {s === 'completed' ? <CheckCircle2 size={13} /> : s === 'active' ? <Loader2 size={13} className="spinner" /> : <Icon size={13} />}
                  </div>
                  <div className="step-info">
                    <div className="step-name" style={{ fontSize: '0.82rem' }}>{step.label}</div>
                    <div className="step-meta" style={{ fontSize: '0.72rem' }}>
                      {s === 'completed' && 'Done'}{s === 'active' && 'Working...'}{s === 'pending' && 'Queued'}{s === 'failed' && 'Error'}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <button
          className="btn btn-primary btn-full"
          onClick={handleGenerate}
        >
          <Mic size={15} /> Generate Voice
        </button>
      )}
    </div>
  );
}
