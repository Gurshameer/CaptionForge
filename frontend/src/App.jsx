import { useState, useCallback, useRef } from 'react';
import Header from './components/Header';
import UploadZone from './components/UploadZone';
import ProgressTracker from './components/ProgressTracker';
import ResultsPanel from './components/ResultsPanel';
import VoicePanel from './components/VoicePanel';

export default function App() {
  const [appState, setAppState] = useState({
    step: 'UPLOAD',
    taskId: null,
    downloadUrl: null,
    detectedLanguage: null,
    srtText: '',
    voiceInput: null,
    error: null,
  });
  const [activeControl, setActiveControl] = useState(0);
  const [activeTool, setActiveTool] = useState('subtitle'); // 'subtitle' | 'voice'
  const toolCardRef = useRef(null);

  const handleUploadSuccess = useCallback((taskId) => {
    setAppState({ step: 'PROCESSING', taskId, downloadUrl: null, detectedLanguage: null, srtText: '', voiceInput: null, error: null });
  }, []);

  const handleProcessingComplete = useCallback((statusData) => {
    setAppState((prev) => ({ ...prev, step: 'COMPLETED', downloadUrl: statusData.download_url, detectedLanguage: statusData.detected_language || 'en' }));
  }, []);

  const handleProcessingFailure = useCallback((errorMessage) => {
    setAppState((prev) => ({ ...prev, step: 'FAILED', error: errorMessage }));
  }, []);

  const handleReset = useCallback(() => {
    setAppState({ step: 'UPLOAD', taskId: null, downloadUrl: null, detectedLanguage: null, srtText: '', voiceInput: null, error: null });
  }, []);

  // Scroll to tool card and switch active tab
  const goToTool = (tool) => {
    setActiveTool(tool);
    setTimeout(() => {
      toolCardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 50);
  };

  return (
    <div className="app-root">
      <Header />

      <section className="hero">
        <div className="hero-blob left"></div>
        <div className="hero-blob right"></div>
        <div className="wrap hero-inner">
          <span className="eyebrow"><span className="dot"></span> AI MEDIA STUDIO</span>
          <h1>Flawless Subtitles.<br/><em>Hyper-Realistic</em> Voice Cloning.</h1>
          <p className="lead">The complete toolkit for video localization and dubbing. Powered by Faster-Whisper and ChatTTSbox TTS.</p>
          <div className="btn-row">
            <button onClick={() => goToTool('subtitle')} className={`btn ${activeTool === 'subtitle' ? 'btn-dark' : 'btn-light'}`}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h10M7 13h6"/></svg>
              Subtitle Generator
            </button>
            <button onClick={() => goToTool('voice')} className={`btn ${activeTool === 'voice' ? 'btn-dark' : 'btn-light'}`}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2M12 19v3"/></svg>
              AI Voice Studio
            </button>
          </div>
      
          <div className="tool-card" ref={toolCardRef}>
            {activeTool === 'subtitle' ? (
              <>
                <UploadZone onUpload={handleUploadSuccess} isProcessing={appState.step !== 'UPLOAD'} />
                {(appState.step === 'PROCESSING' || appState.step === 'FAILED') && (
                  <ProgressTracker taskId={appState.taskId} onComplete={handleProcessingComplete} onFailure={handleProcessingFailure} onReset={handleReset} />
                )}
                {appState.step === 'COMPLETED' && (
                  <ResultsPanel taskId={appState.taskId} downloadUrl={appState.downloadUrl} detectedLanguage={appState.detectedLanguage}
                    onSrtLoaded={(text) => setAppState(prev => ({ ...prev, srtText: text }))}
                    onUseForVoice={(text) => {
                      setAppState(prev => ({ ...prev, voiceInput: { text, ts: Date.now() } }));
                      goToTool('voice');
                    }}
                    onReset={handleReset} />
                )}
              </>
            ) : (
              <VoicePanel voiceInput={appState.voiceInput} defaultLanguage={appState.detectedLanguage || 'en'} />
            )}
          </div>
        </div>
      </section>
      
      <section className="tools-section">
        <div className="wrap">
          <div className="tools-head">
            <div className="eyebrow-label">Core Capabilities</div>
            <h2 className="section-title">Two powerful tools, <em className="em">one</em> studio.</h2>
          </div>
          <div className="tool-grid">
            <div className="tool-feature-card" id="subtitles">
              <div className="feature-media">
                <img
                  src="https://images.unsplash.com/photo-1574717024653-61fd2cf4d44d?w=800&q=80"
                  alt="Video editing software on a laptop"
                  style={{width:'100%',height:'100%',objectFit:'cover',display:'block'}}
                />
              </div>
              <div className="feature-body">
                <div className="feature-icon-row">
                  <div className="feature-icon icon-rust">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h10M7 13h6"/></svg>
                  </div>
                  <h3>Subtitle Generator</h3>
                </div>
                <p>Upload video or paste a YouTube link. Our AI automatically transcribes, timestamps, and generates perfectly synced subtitles in multiple formats.</p>
                <button onClick={() => goToTool('subtitle')} className="feature-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h10M7 13h6"/></svg>
                  Generate Subtitles
                </button>
              </div>
            </div>

            <div className="tool-feature-card" id="voice">
              <div className="feature-media">
                <img
                  src="https://images.unsplash.com/photo-1598488035139-bdbb2231ce04?w=800&q=80"
                  alt="Professional recording studio"
                  style={{width:'100%',height:'100%',objectFit:'cover',display:'block'}}
                />
              </div>
              <div className="feature-body">
                <div className="feature-icon-row">
                  <div className="feature-icon icon-sage">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2M12 19v3"/></svg>
                  </div>
                  <h3>AI Voice Studio</h3>
                </div>
                <p>Generate realistic speech or clone any voice. Fine-tune expressiveness with Exaggeration and CFG Weight controls for broadcast-quality output.</p>
                <button onClick={() => goToTool('voice')} className="feature-btn feature-btn--sage">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2M12 19v3"/></svg>
                  Generate Voice
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>
      
      <section className="controls-section">
        <div className="wrap">
          <div className="controls-head">
            <div className="eyebrow-label">Voice Cloning Controls</div>
            <h2 className="section-title">Fine-tune your <em className="em">output</em> with precision.</h2>
            <p className="section-sub">Understanding the expressiveness parameters will help you get the best output.</p>
          </div>
          <div className="controls-grid">
            <div className="ctrl-list">
              <div className={`ctrl-item ${activeControl === 0 ? 'active' : ''}`} onClick={() => setActiveControl(0)}>
                <div className="ctrl-label">Control 1</div>
                <div className="ctrl-title">Exaggeration</div>
              </div>
              <div className={`ctrl-item ${activeControl === 1 ? 'active' : ''}`} onClick={() => setActiveControl(1)}>
                <div className="ctrl-label">Control 2</div>
                <div className="ctrl-title">CFG Weight</div>
              </div>
              <div className={`ctrl-item ${activeControl === 2 ? 'active' : ''}`} onClick={() => setActiveControl(2)}>
                <div className="ctrl-label">Control 3</div>
                <div className="ctrl-title">The Finest Results</div>
              </div>
            </div>
            <div className="ctrl-panel">
              {activeControl === 0 && (
                <div className="ctrl-panel-content">
                  <div className="ctrl-num">01</div>
                  <h3>Exaggeration</h3>
                  <div className="ctrl-range">Tune 0.0 – 1.0, default 0.5</div>
                  <ul>
                    <li>Controls how much emotion is expressed in synthesized speech.</li>
                    <li>Ranges from low (0.3, flat monotone — great for tutorials, news, or corporate) to high (1.5, highly dramatic for storytelling or emotion-heavy content).</li>
                    <li>Mid point (0.65) suits balanced, natural sounding speech.</li>
                  </ul>
                </div>
              )}
              {activeControl === 1 && (
                <div className="ctrl-panel-content">
                  <div className="ctrl-num">02</div>
                  <h3>CFG Weight</h3>
                  <div className="ctrl-range">Tune 0.0 – 1.0, default 0.5</div>
                  <ul>
                    <li>Controls clarity-to-personality ratio in the voice clone's output.</li>
                    <li>Lower values prioritize crisp, broadcast-clean articulation.</li>
                    <li>Higher values preserve more of the source speaker's unique vocal character.</li>
                  </ul>
                </div>
              )}
              {activeControl === 2 && (
                <div className="ctrl-panel-content">
                  <div className="ctrl-num">03</div>
                  <h3>The Finest Results</h3>
                  <div className="ctrl-range">Best-practice workflow</div>
                  <ul>
                    <li>Use a clean, noise-free reference sample of at least 10 seconds.</li>
                    <li>Combine moderate Exaggeration with balanced CFG Weight for natural narration.</li>
                    <li>Preview a short clip before running the full script through the voice engine.</li>
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
      
      <section className="lang-section">
        <div className="wrap">
          <div className="lang-head">
            <div className="eyebrow-label">Global Reach</div>
            <h2 className="section-title"><em className="em">12 languages</em> supported.</h2>
            <p className="section-sub" style={{margin:'0 auto'}}>Localize your content for audiences worldwide with native-quality transcription and dubbing.</p>
          </div>
          <div className="lang-grid">
            <div className="lang-card"><div className="lang-code">EN</div><div className="lang-name">English</div></div>
            <div className="lang-card"><div className="lang-code">HI</div><div className="lang-name">Hindi</div></div>
            <div className="lang-card"><div className="lang-code">FR</div><div className="lang-name">French</div></div>
            <div className="lang-card"><div className="lang-code">DE</div><div className="lang-name">German</div></div>
            <div className="lang-card"><div className="lang-code">ES</div><div className="lang-name">Spanish</div></div>
            <div className="lang-card"><div className="lang-code">IT</div><div className="lang-name">Italian</div></div>
            <div className="lang-card"><div className="lang-code">PT</div><div className="lang-name">Portuguese</div></div>
            <div className="lang-card"><div className="lang-code">RU</div><div className="lang-name">Russian</div></div>
            <div className="lang-card"><div className="lang-code">JA</div><div className="lang-name">Japanese</div></div>
            <div className="lang-card"><div className="lang-code">KO</div><div className="lang-name">Korean</div></div>
            <div className="lang-card"><div className="lang-code">ZH</div><div className="lang-name">Chinese</div></div>
            <div className="lang-card"><div className="lang-code">AR</div><div className="lang-name">Arabic</div></div>
          </div>
        </div>
      </section>
      
      <section className="specs-section">
        <div className="wrap specs-grid">
          <div className="specs-visual">
            <img
              src="https://images.unsplash.com/photo-1550745165-9bc0b252726f?w=900&q=90"
              alt="Neon sound wave visualization"
              style={{width:'100%',height:'100%',objectFit:'cover',display:'block',borderRadius:'inherit'}}
            />
          </div>
          <div className="specs-head">
            <div className="specs-eyebrow">TECHNICAL SPECIFICATIONS</div>
            <h2 className="specs-title">Voice Engine <em className="em">Specs.</em></h2>
            <ul className="specs-list">
              <li><span className="check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5L20 7"/></svg></span><span>Realtime phonetic voices (English, multilingual)</span></li>
              <li><span className="check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5L20 7"/></svg></span><span>State-of-the-art voice cloning via ChatTTSbox TTS</span></li>
              <li><span className="check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5L20 7"/></svg></span><span>Exaggeration + CFG Weight expressiveness controls</span></li>
              <li><span className="check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5L20 7"/></svg></span><span>Upload .srt or .TXT script to auto-dub</span></li>
              <li><span className="check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5L20 7"/></svg></span><span>Speaker Space for multi-speaker audio</span></li>
              <li><span className="check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5L20 7"/></svg></span><span>Max video size: 100MB per upload</span></li>
              <li><span className="check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5L20 7"/></svg></span><span>Voice clone host: A100 / H100 GPU [PCIe / HGX]</span></li>
              <li><span className="check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5L20 7"/></svg></span><span>Enterprise license available upon request</span></li>
              <li><span className="check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5L20 7"/></svg></span><span><strong>Quick Start:</strong> Upload a video and get subtitles in under 60 seconds</span></li>
            </ul>
          </div>
        </div>
      </section>
      
      <section className="steps-section">
        <div className="wrap">
          <div className="steps-head">
            <div className="eyebrow-label">Get Started</div>
            <h2 className="section-title">Four steps to <em className="em">perfect</em> audio.</h2>
          </div>
          <div className="steps-grid">
            <div className="step-card">
              <div className="step-num">1</div>
              <h3>Upload</h3>
              <p>Upload video or paste YouTube URL</p>
            </div>
            <div className="step-card">
              <div className="step-num">2</div>
              <h3>Process</h3>
              <p>AI transcribes and generates subtitles</p>
            </div>
            <div className="step-card">
              <div className="step-num">3</div>
              <h3>Clone</h3>
              <p>Download SRT/VTT or burn into video</p>
            </div>
            <div className="step-card">
              <div className="step-num">4</div>
              <h3>Dub</h3>
              <p>Use script for AI voice dubbing</p>
            </div>
          </div>
        </div>
      </section>
      
    </div>
  );
}
