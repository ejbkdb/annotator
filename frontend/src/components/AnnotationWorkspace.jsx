// frontend/src/components/AnnotationWorkspace.jsx

import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import TimeSeriesChart from './TimeSeriesChart';
import EventLog from './EventLog';
import './AnnotationWorkspace.css';

import { parseISOString, formatForInput } from '../utils/time';

const DURATION_OPTIONS = [5, 10, 20, 50, 100];
const FIXED_WINDOW_OPTIONS = [5, 8, 10]; // seconds

const defaultAnnotationState = {
    vehicle_type: '', location: 'tarmac', action: 'driveby',
    direction: 'na', // --- MODIFIED: Set default to 'na' ---
    annotator_notes: ''
};

function AnnotationWorkspace({ collections, selectedCollection, setSelectedCollection, jumpToData, activeReviewEvent }) {
  const [refinedAnnotations, setRefinedAnnotations] = useState([]);
  const [vehicleConfigs, setVehicleConfigs] = useState([]);
  const [availableRange, setAvailableRange] = useState({ start: null, end: null });
  const [error, setError] = useState('');
  
  const [startTime, setStartTime] = useState(null);
  const [durationSecs, setDurationSecs] = useState(10);
  const [points, setPoints] = useState(2000);

  const [chartData, setChartData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const [selectionMode, setSelectionMode] = useState('manual');
  const [fixedWindowSize, setFixedWindowSize] = useState(8);
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectionRange, setSelectionRange] = useState(null);
  const [activeAnnotation, setActiveAnnotation] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef(new Audio());

  useEffect(() => {
    if (jumpToData) {
      setStartTime(jumpToData.startTime);
      setDurationSecs(jumpToData.durationSecs);
      setRefinedAnnotations([]);
    }
  }, [jumpToData]);

  useEffect(() => {
    axios.get('/api/config/vehicles').then(res => setVehicleConfigs(res.data));
  }, []);

  const fetchRefinedAnnotations = useCallback(async () => {
    if (activeReviewEvent?.id) {
        try {
            const response = await axios.get('/api/annotations/refined', { params: { parent_event_id: activeReviewEvent.id } });
            setRefinedAnnotations(response.data);
        } catch (err) {
            console.error("Could not fetch refined annotations", err);
        }
    }
  }, [activeReviewEvent]);

  useEffect(() => {
    fetchRefinedAnnotations();
  }, [fetchRefinedAnnotations]);

  useEffect(() => {
    if (!selectedCollection) {
      setStartTime(null); setAvailableRange({ start: null, end: null }); setChartData([]);
      return;
    }
    const fetchCollectionInfo = async () => {
      try {
        setError('');
        const response = await axios.get(`/api/audio/collections/${selectedCollection}/info`);
        const { start, end } = response.data.time_range;
        const startUTC = parseISOString(start);
        const endUTC = parseISOString(end);
        setAvailableRange({ start: startUTC, end: endUTC });
        if (!jumpToData) { setStartTime(startUTC); }
      } catch (err) {
        setError(`Could not fetch info for '${selectedCollection}': ${err.response?.data?.detail || err.message}`);
        setAvailableRange({ start: null, end: null }); setStartTime(null);
      }
    };
    fetchCollectionInfo();
    setRefinedAnnotations([]);
  }, [selectedCollection, jumpToData]);

  useEffect(() => {
    if (!selectedCollection || !startTime) return;
    const endTime = new Date(startTime.getTime() + durationSecs * 1000);
    const fetchWaveformData = async () => {
      setIsLoading(true); setError('');
      try {
        const response = await axios.get('/api/audio/waveform', { params: { collection: selectedCollection, start: startTime.toISOString(), end: endTime.toISOString(), points: points } });
        setChartData(response.data);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to fetch waveform'); setChartData([]);
      } finally { setIsLoading(false); }
    };
    fetchWaveformData();
  }, [selectedCollection, startTime, durationSecs, points]);
  
  const handleChartHover = (timestamp) => {
    if (selectionMode !== 'fixed') return;

    const hoverDate = parseISOString(timestamp);
    const halfWindowMs = (fixedWindowSize * 1000) / 2;
    const start = new Date(hoverDate.getTime() - halfWindowMs);
    const end = new Date(hoverDate.getTime() + halfWindowMs);
    setSelectionRange({ start, end });
  };

  const handleChartClick = (timestamp) => {
    const clickedDate = parseISOString(timestamp);

    if (selectionMode === 'fixed') {
        const halfWindowMs = (fixedWindowSize * 1000) / 2;
        const start = new Date(clickedDate.getTime() - halfWindowMs);
        const end = new Date(clickedDate.getTime() + halfWindowMs);
        setSelectionRange({ start, end });
        setActiveAnnotation({ ...defaultAnnotationState, vehicle_type: activeReviewEvent?.vehicle_type || '' });
        return;
    }
    if (!isSelecting) {
      setIsSelecting(true);
      setSelectionRange({ start: clickedDate, end: null });
      setActiveAnnotation(null);
    } else {
      let [finalStart, finalEnd] = [selectionRange.start, clickedDate].sort((a,b) => a - b);
      setSelectionRange({ start: finalStart, end: finalEnd });
      setIsSelecting(false);
      setActiveAnnotation({ ...defaultAnnotationState, vehicle_type: activeReviewEvent?.vehicle_type || '' });
    }
  };

  const cancelSelection = () => {
    setIsSelecting(false); setSelectionRange(null); setActiveAnnotation(null);
  };

  const handlePlayAudio = async () => {
    if (!selectionRange?.start || !selectionRange?.end) return;
    setIsPlaying(true);
    try {
      const response = await axios.get('/api/audio/raw', {
        params: { collection: selectedCollection, start: selectionRange.start.toISOString(), end: selectionRange.end.toISOString() },
        responseType: 'arraybuffer',
      });
      const audioUrl = URL.createObjectURL(new Blob([response.data], { type: 'audio/wav' }));
      audioRef.current.src = audioUrl;
      audioRef.current.play();
      audioRef.current.onended = () => { setIsPlaying(false); URL.revokeObjectURL(audioUrl); };
    } catch (err) {
      setError('Failed to fetch or play audio clip.'); setIsPlaying(false);
    }
  };

  const handleSaveAnnotation = async () => {
    if (!activeAnnotation.vehicle_type || !activeReviewEvent) {
        alert("Cannot save: vehicle type and an active review session are required.");
        return;
    }
    const payload = {
        parent_event_id: activeReviewEvent.id,
        source_collection: selectedCollection,
        start_timestamp: selectionRange.start.toISOString(),
        end_timestamp: selectionRange.end.toISOString(),
        ...activeAnnotation
    };
    try {
        const response = await axios.post('/api/annotations/refined', payload);
        setRefinedAnnotations(prev => [...prev, response.data]);
        cancelSelection();
    } catch (err) { setError(`Failed to save annotation: ${err.response?.data?.detail || err.message}`); }
  };

  const handleNavigate = (direction) => {
    if (!startTime || !availableRange.start) return;
    const hopMs = durationSecs * 1000;
    const currentMs = startTime.getTime();
    let newMs = direction === 'next' ? currentMs + hopMs : currentMs - hopMs;
    const availableStartMs = availableRange.start.getTime();
    const availableEndMs = availableRange.end.getTime();
    if (newMs < availableStartMs) newMs = availableStartMs;
    if (newMs >= (availableEndMs - hopMs)) newMs = availableEndMs - hopMs;
    setStartTime(new Date(newMs));
  };

  const handleTimeInputChange = (e) => {
    const userDate = new Date(e.target.value + 'Z');
    if (!isNaN(userDate)) { setStartTime(userDate); }
  };

  const handleAnnotationInputChange = (e) => {
    const { name, value } = e.target;
    setActiveAnnotation(p => ({ ...p, [name]: value }));
  };

  return (
    <div className="workspace-container">
      <div className="workspace-controls">
        <label htmlFor="collection-select">Select Data Collection:</label>
        <select id="collection-select" value={selectedCollection} onChange={(e) => setSelectedCollection(e.target.value)}>
          <option value="">-- Choose a collection --</option>
          {collections.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {error && <p style={{ color: 'red', padding: '10px' }}>{error}</p>}

      {availableRange.start && (
        <>
        <div className="time-controls-panel">
          <div className="control-group">
            <span className="control-label">Window:</span>
            <div className="button-tabs">
              {DURATION_OPTIONS.map(d => <button key={d} className={`tab-button ${d === durationSecs ? 'selected' : ''}`} onClick={() => setDurationSecs(d)}>{d}s</button>)}
            </div>
          </div>
          <div className="control-group navigation-group">
            <button className="nav-button" onClick={() => handleNavigate('prev')}>{'<<'} Prev</button>
            <div className="start-time-input"><label htmlFor="start-time">Start Time (UTC):</label><input type="datetime-local" id="start-time" value={formatForInput(startTime)} onChange={handleTimeInputChange} step="1"/></div>
            <button className="nav-button" onClick={() => handleNavigate('next')}>Next {'>>'}</button>
          </div>
        </div>
        <div className="time-controls-panel" style={{justifyContent: "flex-start"}}>
            <div className="control-group">
                <span className="control-label">Selection Mode:</span>
                <div className="button-tabs">
                    <button className={`tab-button ${selectionMode === 'manual' ? 'selected' : ''}`} onClick={() => setSelectionMode('manual')}>Manual</button>
                    <button className={`tab-button ${selectionMode === 'fixed' ? 'selected' : ''}`} onClick={() => setSelectionMode('fixed')}>Fixed Window</button>
                </div>
            </div>
            {selectionMode === 'fixed' && (
                <div className="control-group">
                    <span className="control-label">Window Size:</span>
                    <div className="button-tabs">
                        {FIXED_WINDOW_OPTIONS.map(d => <button key={d} className={`tab-button ${d === fixedWindowSize ? 'selected' : ''}`} onClick={() => setFixedWindowSize(d)}>{d}s</button>)}
                    </div>
                </div>
            )}
        </div>
        </>
      )}

      {isLoading ? ( <div className="loading-message">Loading Chart Data...</div> ) : (
        <TimeSeriesChart 
          chartData={chartData} 
          onChartClick={handleChartClick} 
          onChartHover={handleChartHover}
          selection={selectionRange} 
        />
      )}
      
      {isSelecting && (
        <div className="selection-prompt">
          Click a second point on the chart to finish selection... (or{' '}
          <button className="link-button" onClick={cancelSelection}>Cancel</button>)
        </div>
      )}

      {activeAnnotation && selectionRange?.end && (
        <div className="annotation-form">
          <h4>New Refined Annotation</h4>
          <p>Duration: {((selectionRange.end - selectionRange.start)/1000).toFixed(2)}s</p>
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px'}}>
              <select name="vehicle_type" value={activeAnnotation.vehicle_type} onChange={handleAnnotationInputChange}>
                <option value="">-- Select Vehicle --</option>
                {vehicleConfigs.map(v => <option key={v.id} value={v.id}>{v.displayName}</option>)}
              </select>
              <select name="location" value={activeAnnotation.location} onChange={handleAnnotationInputChange}>
                <option value="tarmac">Tarmac</option><option value="fastpass">Fastpass</option><option value="jungle">Jungle</option>
              </select>
              <select name="action" value={activeAnnotation.action} onChange={handleAnnotationInputChange}>
                <option value="driveby">Driveby</option><option value="rev">Rev</option><option value="idle">Idle</option><option value="flying">Flying</option><option value="hover">Hover</option>
              </select>
              {/* --- MODIFIED: Added 'na' option to dropdown --- */}
              <select name="direction" value={activeAnnotation.direction} onChange={handleAnnotationInputChange}>
                <option value="towards_de">Towards DE</option>
                <option value="towards_103">Towards 103</option>
                <option value="na">N/A</option>
              </select>
          </div>
          <textarea name="annotator_notes" placeholder="Notes..." value={activeAnnotation.annotator_notes} onChange={handleAnnotationInputChange}/>
          <div className="form-actions">
            <button onClick={handlePlayAudio} disabled={isPlaying}>{isPlaying ? 'Playing...' : 'Play Audio'}</button>
            <button onClick={handleSaveAnnotation} className="save-button">Save Annotation</button>
            <button onClick={cancelSelection}>Cancel</button>
          </div>
        </div>
      )}
      
      <div className="event-log-container">
        <EventLog events={refinedAnnotations} />
      </div>
    </div>
  );
}

export default AnnotationWorkspace;