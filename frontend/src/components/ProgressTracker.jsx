import { useEffect, useState } from 'react';
import { apiUrl } from '../api';
import { 
  Music, 
  Languages, 
  Sparkles, 
  FileText, 
  Loader2, 
  AlertCircle, 
  CheckCircle2 
} from 'lucide-react';

const STEPS = [
  { id: 'audio_extraction', label: 'Audio Extraction', progress: 15, icon: Music },
  { id: 'speech_recognition', label: 'Speech Recognition', progress: 40, icon: Languages },
  { id: 'transcript_enhancement', label: 'Transcript Enhancement', progress: 70, icon: Sparkles },
  { id: 'subtitle_generation', label: 'Subtitle Generation', progress: 90, icon: FileText },
];

export default function ProgressTracker({ taskId, onComplete, onFailure }) {
  const [statusData, setStatusData] = useState({
    status: 'PENDING',
    progress: 0,
    current_step: 'upload_complete',
    detected_language: null,
    error: null,
  });

  useEffect(() => {
    if (!taskId) return;

    let intervalId = null;

    const pollStatus = async () => {
      try {
        const response = await fetch(apiUrl(`/api/v1/subtitles/status/${taskId}`));
        if (!response.ok) {
          throw new Error(`Failed to fetch status: ${response.statusText}`);
        }
        const data = await response.json();
        setStatusData(data);

        if (data.status === 'COMPLETED') {
          clearInterval(intervalId);
          if (onComplete) onComplete(data);
        } else if (data.status === 'FAILED') {
          clearInterval(intervalId);
          if (onFailure) onFailure(data.error || 'Subtitle generation failed');
        }
      } catch (err) {
        console.error('Error polling status:', err);
        // We don't immediately fail to handle transient network issues, 
        // but if it persists, we show an error.
      }
    };

    // Poll immediately
    pollStatus();

    // Start interval
    intervalId = setInterval(pollStatus, 2000);

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [taskId, onComplete, onFailure]);

  const { status, progress, current_step, detected_language, error } = statusData;

  const getStepStatus = (stepId, stepProgress) => {
    if (status === 'FAILED') return 'failed';
    if (status === 'COMPLETED') return 'completed';
    
    // Find current active step index
    const currentStepIndex = STEPS.findIndex(s => s.id === current_step);
    const thisStepIndex = STEPS.findIndex(s => s.id === stepId);

    if (currentStepIndex === -1) {
      return 'pending'; // If we're pending/upload complete
    }

    if (thisStepIndex < currentStepIndex) return 'completed';
    if (thisStepIndex === currentStepIndex) return 'active';
    return 'pending';
  };

  return (
    <div className="card animate-fade-in" style={{ borderColor: 'var(--primary)', boxShadow: 'var(--shadow-glow)' }}>
      <div className="progress-header">
        <div className="status-badge-container">
          <span className={`status-badge ${status.toLowerCase()}`}>
            {status === 'PROCESSING' && <Loader2 className="spinner" size={14} />}
            {status === 'COMPLETED' && <CheckCircle2 size={14} />}
            {status === 'FAILED' && <AlertCircle size={14} />}
            {status}
          </span>
          {detected_language && (
            <span className="lang-badge">
              Detected Lang: <strong>{detected_language.toUpperCase()}</strong>
            </span>
          )}
        </div>
        <span className="progress-percentage">{Math.round(progress)}%</span>
      </div>

      {/* Main progress bar */}
      <div className="progress-bar-container">
        <div 
          className={`progress-bar-fill ${status === 'FAILED' ? 'failed' : ''}`}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Steps Pipeline */}
      <div className="pipeline-steps">
        {STEPS.map((step) => {
          const Icon = step.icon;
          const stepStatus = getStepStatus(step.id, step.progress);

          return (
            <div key={step.id} className={`pipeline-step ${stepStatus}`}>
              <div className="step-icon-wrapper">
                <Icon className="step-icon" size={20} />
                {stepStatus === 'completed' && (
                  <div className="step-check">
                    <CheckCircle2 size={12} fill="var(--success)" stroke="white" />
                  </div>
                )}
              </div>
              <span className="step-label">{step.label}</span>
              <span className="step-sub-status">
                {stepStatus === 'completed' && 'Done'}
                {stepStatus === 'active' && 'Processing...'}
                {stepStatus === 'pending' && 'Queued'}
                {stepStatus === 'failed' && 'Failed'}
              </span>
            </div>
          );
        })}
      </div>

      {status === 'FAILED' && (
        <div className="error-banner animate-slide-up">
          <AlertCircle size={20} className="error-icon" />
          <div className="error-details">
            <h4>Generation Failed</h4>
            <p>{error || 'An unexpected error occurred during processing.'}</p>
          </div>
        </div>
      )}
    </div>
  );
}
