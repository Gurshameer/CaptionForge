import { useState, useEffect } from 'react';
import { Download, Copy, Check, FileCode, AlertCircle, RefreshCw } from 'lucide-react';
import { apiUrl } from '../api';

export default function ResultsPanel({ taskId, downloadUrl, onReset }) {
  const [srtContent, setSrtContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const fetchSrt = async () => {
      if (!downloadUrl) return;
      try {
        setLoading(true);
        const response = await fetch(apiUrl(downloadUrl));
        if (!response.ok) {
          throw new Error('Failed to retrieve SRT content.');
        }
        const text = await response.text();
        setSrtContent(text);
        setError(null);
      } catch (err) {
        console.error('Error fetching SRT:', err);
        setError('Could not load preview. You can still download the file directly.');
      } finally {
        setLoading(false);
      }
    };

    fetchSrt();
  }, [downloadUrl]);

  const handleCopy = async () => {
    if (!srtContent) return;
    try {
      await navigator.clipboard.writeText(srtContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  return (
    <div className="card animate-scale-up">
      <div className="card__title" style={{ display: 'flex', justifyContent: 'space-between', borderBottom: 'none' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <FileCode className="card__title-icon" size={20} />
          <div>
            <div style={{ fontSize: '1.1rem', fontWeight: '700' }}>Generated Subtitles</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Ready for download and preview</div>
          </div>
        </div>

        <div className="action-buttons">
          <button 
            onClick={handleCopy} 
            className={`btn btn-secondary btn-icon-only ${copied ? 'success' : ''}`}
            disabled={loading || !!error || !srtContent}
            title="Copy to clipboard"
          >
            {copied ? <Check size={18} /> : <Copy size={18} />}
          </button>
          
          <a 
            href={apiUrl(downloadUrl)} 
            download
            className="btn btn-primary btn-icon"
          >
            <Download size={18} />
            <span>Download .SRT</span>
          </a>
        </div>
      </div>

      <div className="preview-container">
        {loading ? (
          <div className="preview-placeholder loading">
            <RefreshCw className="spinner" size={32} />
            <p>Loading subtitle preview...</p>
          </div>
        ) : error ? (
          <div className="preview-placeholder error">
            <AlertCircle size={32} className="error-icon" />
            <p>{error}</p>
          </div>
        ) : (
          <pre className="srt-preview">
            <code>{srtContent}</code>
          </pre>
        )}
      </div>

      <div className="results-footer">
        <p className="credits">Enhanced via Gemma-3 12B &amp; Faster-Whisper</p>
        <button onClick={onReset} className="btn btn-text">
          Upload Another Video
        </button>
      </div>
    </div>
  );
}
