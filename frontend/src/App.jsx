import { useState, useCallback } from 'react';
import Header from './components/Header';
import InfoBox from './components/InfoBox';
import UploadZone from './components/UploadZone';
import ProgressTracker from './components/ProgressTracker';
import ResultsPanel from './components/ResultsPanel';

export default function App() {
  const [appState, setAppState] = useState({
    step: 'UPLOAD', // UPLOAD, PROCESSING, COMPLETED, FAILED
    taskId: null,
    downloadUrl: null,
    error: null,
  });

  const handleUploadSuccess = useCallback((taskId) => {
    setAppState({
      step: 'PROCESSING',
      taskId: taskId,
      downloadUrl: null,
      error: null,
    });
  }, []);

  const handleProcessingComplete = useCallback((statusData) => {
    setAppState((prev) => ({
      ...prev,
      step: 'COMPLETED',
      downloadUrl: statusData.download_url,
    }));
  }, []);

  const handleProcessingFailure = useCallback((errorMessage) => {
    setAppState((prev) => ({
      ...prev,
      step: 'FAILED',
      error: errorMessage,
    }));
  }, []);

  const handleReset = useCallback(() => {
    setAppState({
      step: 'UPLOAD',
      taskId: null,
      downloadUrl: null,
      error: null,
    });
  }, []);

  return (
    <div className="app-container">
      <main className="content-layout">
        <Header />

        <div className="dashboard-grid">
          <aside className="sidebar-column">
            <InfoBox />
          </aside>
          
          <section className="main-column">
            {/* Show Upload Zone unless processing has started and not failed */}
            {appState.step !== 'COMPLETED' && (
              <UploadZone 
                onUpload={handleUploadSuccess} 
                isProcessing={appState.step === 'PROCESSING'} 
              />
            )}

            {(appState.step === 'PROCESSING' || appState.step === 'FAILED') && (
              <ProgressTracker
                taskId={appState.taskId}
                onComplete={handleProcessingComplete}
                onFailure={handleProcessingFailure}
              />
            )}

            {appState.step === 'COMPLETED' && (
              <ResultsPanel
                taskId={appState.taskId}
                downloadUrl={appState.downloadUrl}
                onReset={handleReset}
              />
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
