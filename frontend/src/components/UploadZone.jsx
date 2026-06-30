import { useRef, useState } from 'react';
import { Upload, Film, X, Video, Link as LinkIcon } from 'lucide-react';
import { apiUrl } from '../api';

const ALLOWED_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.mpeg', '.wmv'];
const MAX_SIZE_MB = 100;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

export default function UploadZone({ onUpload, isProcessing }) {
  const [tab, setTab] = useState('file');
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef(null);

  function validateFile(f) {
    const ext = '.' + f.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) return `Unsupported: ${ext}`;
    if (f.size > MAX_SIZE_BYTES) return `Too large (${formatFileSize(f.size)}). Max ${MAX_SIZE_MB} MB.`;
    return null;
  }

  function handleSelect(f) {
    setError('');
    const err = validateFile(f);
    if (err) { setError(err); setFile(null); return; }
    setFile(f);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleSelect(f);
  }

  async function handleUpload() {
    if (tab === 'file' && !file) return;
    if (tab === 'url' && !url.trim()) return;
    setUploading(true);
    setError('');
    try {
      let res;
      if (tab === 'file') {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('language', 'auto');
        res = await fetch(apiUrl('/api/v1/subtitles/upload'), { method: 'POST', body: fd });
      } else {
        res = await fetch(apiUrl('/api/v1/subtitles/url'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url.trim(), language: 'auto' }),
        });
      }
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Upload failed.'); setUploading(false); return; }
      setUploading(false);
      setFile(null);
      setUrl('');
      if (inputRef.current) inputRef.current.value = '';
      onUpload(data.task_id);
    } catch {
      setError('Network error. Is the backend running?');
      setUploading(false);
    }
  }

  const disabled = isProcessing || uploading;

  return (
    <>
      <div className="tool-head">
        <div className="tool-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h10M7 13h6"/></svg>
        </div>
        <div>
          <h3>Subtitle Generator</h3>
          <p>Upload video or paste a YouTube link</p>
        </div>
      </div>

      <div className="seg-row">
        <div className={`seg-btn ${tab === 'file' ? 'active' : ''}`} onClick={() => { setTab('file'); setError(''); }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 16V4M12 4l-4 4M12 4l4 4M5 20h14"/></svg>
          Upload Video
        </div>
        <div className={`seg-btn ${tab === 'url' ? 'active' : ''}`} onClick={() => { setTab('url'); setError(''); }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="6" width="18" height="13" rx="2"/><path d="M9 10l5 3-5 3v-6z" fill="currentColor" stroke="none"/></svg>
          YouTube URL
        </div>
      </div>

      {tab === 'file' ? (
        <>
          <div
            className={`upload-zone ${dragOver ? 'upload-zone--dragover' : ''} ${disabled ? 'upload-zone--disabled' : ''}`}
            onClick={() => !disabled && inputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={(e) => { e.preventDefault(); setDragOver(false); }}
            style={{border: '2px dashed var(--line)', borderRadius: '12px', padding: '40px 24px', textAlign: 'center', cursor: 'pointer', background: 'var(--cream-soft)', marginBottom: '22px'}}
          >
            <div style={{color: 'var(--ink-soft)', marginBottom: '12px'}}><Upload size={36} style={{margin:'0 auto'}}/></div>
            <p style={{fontSize: '0.95rem', fontWeight: 500, color: 'var(--ink)', marginBottom: '6px'}}>
              Drop your video here or <span style={{color: 'var(--rust)', fontWeight: 600}}>browse files</span>
            </p>
            <p style={{fontSize: '0.8rem', color: 'var(--ink-soft)'}}>MP4, MKV, AVI, MOV, WebM — up to {MAX_SIZE_MB} MB</p>
            <input
              ref={inputRef}
              type="file"
              style={{display: 'none'}}
              accept={ALLOWED_EXTENSIONS.join(',')}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleSelect(f); }}
              disabled={disabled}
            />
          </div>

          {file && (
            <div style={{display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 14px', background: 'var(--cream)', border: '1px solid var(--line)', borderRadius: '10px', marginBottom: '22px'}}>
              <Film size={16} />
              <div style={{flex:1, overflow:'hidden'}}>
                <div style={{fontWeight: 600, fontSize: '0.85rem'}}>{file.name}</div>
                <div style={{fontSize: '0.75rem', color: 'var(--ink-soft)'}}>{formatFileSize(file.size)}</div>
              </div>
              <button onClick={() => { setFile(null); if (inputRef.current) inputRef.current.value = ''; }} disabled={disabled} style={{background:'none',border:'none',cursor:'pointer',color:'var(--ink-soft)'}}>
                <X size={14} />
              </button>
            </div>
          )}
        </>
      ) : (
        <div style={{marginBottom: '22px'}}>
          <p className="helper-text">Paste a public YouTube URL. The video will be downloaded and processed automatically.</p>
          <div style={{position: 'relative'}}>
            <LinkIcon size={16} style={{position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-soft)'}} />
            <input
              type="text"
              placeholder="https://www.youtube.com/watch?v=..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleUpload()}
              disabled={disabled}
              style={{width: '100%', padding: '12px 14px 12px 42px', background: 'var(--cream)', border: '1px solid var(--line)', borderRadius: '12px', color: 'var(--ink)', fontFamily: 'inherit', fontSize: '0.9rem', outline: 'none'}}
            />
          </div>
        </div>
      )}

      {error && <div style={{padding: '10px 14px', background: 'rgba(192,96,42,0.08)', border: '1px solid rgba(192,96,42,0.2)', borderRadius: '10px', fontSize: '0.82rem', color: 'var(--rust)', marginBottom: '22px'}}>{error}</div>}

      {!isProcessing && (
        <button className="cta-full" onClick={handleUpload} disabled={disabled}>
          {uploading ? (
            <><span className="spinner" style={{display:'inline-block', border:'2px solid rgba(255,255,255,0.3)', borderTopColor:'#fff', borderRadius:'50%', width:'16px', height:'16px', marginRight:'8px'}}></span> Processing...</>
          ) : (
            <><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l1.8 4.7L18 9l-4.2 1.3L12 15l-1.8-4.7L6 9l4.2-1.3L12 3z"/></svg> Generate Subtitles</>
          )}
        </button>
      )}
    </>
  );
}
