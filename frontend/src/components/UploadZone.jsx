import { useRef, useState } from 'react';
import { Upload, Film, X } from 'lucide-react';

const ALLOWED_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.mpeg', '.wmv'];
const MAX_SIZE_MB = 100;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

export default function UploadZone({ onUpload, isProcessing }) {
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef(null);

  function validateFile(f) {
    const ext = '.' + f.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Unsupported format "${ext}". Supported: ${ALLOWED_EXTENSIONS.join(', ')}`;
    }
    if (f.size > MAX_SIZE_BYTES) {
      return `File too large (${formatFileSize(f.size)}). Max size: ${MAX_SIZE_MB} MB.`;
    }
    return null;
  }

  function handleSelect(f) {
    setError('');
    const validationError = validateFile(f);
    if (validationError) {
      setError(validationError);
      setFile(null);
      return;
    }
    setFile(f);
  }

  function handleInputChange(e) {
    const f = e.target.files?.[0];
    if (f) handleSelect(f);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleSelect(f);
  }

  function handleDragOver(e) {
    e.preventDefault();
    setDragOver(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    setDragOver(false);
  }

  function handleRemove() {
    setFile(null);
    setError('');
    if (inputRef.current) inputRef.current.value = '';
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/v1/subtitles/upload', {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.detail || 'Upload failed. Please try again.');
        setUploading(false);
        return;
      }

      setUploading(false);
      setFile(null);
      if (inputRef.current) inputRef.current.value = '';
      onUpload(data.task_id);
    } catch (err) {
      setError('Network error. Is the backend running?');
      setUploading(false);
    }
  }

  const disabled = isProcessing || uploading;

  return (
    <div className="card animate-in">
      <div className="card__title">
        <Upload size={18} className="card__title-icon" />
        Upload Video
      </div>

      <div
        className={`upload-zone ${dragOver ? 'upload-zone--dragover' : ''} ${disabled ? 'upload-zone--disabled' : ''}`}
        onClick={() => !disabled && inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <div className="upload-zone__icon">
          <Upload size={40} />
        </div>
        <p className="upload-zone__text">
          Drag & drop your video here or <span>browse files</span>
        </p>
        <p className="upload-zone__hint">
          MP4, MKV, AVI, MOV, WebM — up to {MAX_SIZE_MB} MB
        </p>
        <input
          ref={inputRef}
          type="file"
          className="upload-zone__input"
          accept={ALLOWED_EXTENSIONS.join(',')}
          onChange={handleInputChange}
          disabled={disabled}
        />
      </div>

      {file && (
        <div className="file-info">
          <Film size={20} className="file-info__icon" />
          <div className="file-info__details">
            <div className="file-info__name">{file.name}</div>
            <div className="file-info__size">{formatFileSize(file.size)}</div>
          </div>
          <button className="file-info__remove" onClick={handleRemove} disabled={disabled}>
            <X size={16} />
          </button>
        </div>
      )}

      {error && (
        <div className="error-box" style={{ marginTop: 'var(--space-md)' }}>
          <span className="error-box__icon">⚠</span>
          <span>{error}</span>
        </div>
      )}

      <button
        className="btn btn--primary btn--full"
        onClick={handleUpload}
        disabled={!file || disabled}
      >
        {uploading ? (
          <>
            <span className="spinner" />
            Uploading…
          </>
        ) : (
          <>
            <Upload size={16} />
            Generate Subtitles
          </>
        )}
      </button>
    </div>
  );
}
