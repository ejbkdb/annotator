// frontend/src/components/AnnotationWorkspace.jsx

import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import TimeSeriesChart from './TimeSeriesChart';
import EventLog from './EventLog';
import './AnnotationWorkspace.css';

const DURATION_OPTIONS = [5, 10, 20, 50, 100];

function AnnotationWorkspace({ collections, selectedCollection, setSelectedCollection }) {
  const [events, setEvents] = useState([]);
  const [vehicleConfigs, setVehicleConfigs] = useState([]);
  const [availableRange, setAvailableRange] = useState({ start: null, end: null });
  const [error, setError] = useState('');
  
  const [startTime, setStartTime] = useState(null);
  const [durationSecs, setDurationSecs] = useState(10);
  const [points, setPoints] = useState(2000);

  const [chartData, setChartData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  // State for the annotation workflow
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectionRange, setSelectionRange] = useState(null);
  const [activeAnnotation, setActiveAnnotation] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef(new Audio());

  // Fetch vehicle configs for the form on component mount
  useEffect(() => {
    axios.get('/api/config/vehicles').then(res => setVehicleConfigs(res.data));
  }, []);

  // Fetch initial collection info
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
        const startDate = new Date(start);
        const endDate = new Date(end);
        setAvailableRange({ start: startDate, end: endDate });
        setStartTime(startDate);
      } catch (err) {
        const errorMsg = err.response?.data?.detail || err.message;
        setError(`Could not fetch time range for '${selectedCollection}': ${errorMsg}`);
        setAvailableRange({ start: null, end: null });
        setStartTime(null);
      }
    };
    fetchCollectionInfo();
    setEvents([]);
  }, [selectedCollection]);

  // Fetch waveform data whenever the view changes
  useEffect(() => {
    if (!selectedCollection || !startTime) return;
    const endTime = new Date(startTime.getTime() + durationSecs * 1000);
    const fetchWaveformData = async () => {
      setIsLoading(true); setError('');
      try {
        const response = await axios.get('/api/audio/waveform', {
          params: {
            collection: selectedCollection,
            start: startTime.toISOString(),
            end: endTime.toISOString(),
            points: points,
          },
        });
        setChartData(response.data);
      } catch (err) {
        const errorMsg = err.response?.data?.detail || 'Failed to fetch waveform';
        setError(errorMsg); setChartData([]);
      } finally { setIsLoading(false); }
    };
    fetchWaveformData();
  }, [selectedCollection, startTime, durationSecs, points]);

  const handleChartClick = (timestamp) => {
    if (!isSelecting) {
      setIsSelecting(true);
      setSelectionRange({ start: timestamp, end: null });
      setActiveAnnotation(null);
    } else {
      let finalStart = selectionRange.start;
      let finalEnd = timestamp;
      if (new Date(finalEnd) < new Date(finalStart)) {
        [finalStart, finalEnd] = [finalEnd, finalStart];
      }
      setSelectionRange({ start: finalStart, end: finalEnd });
      setIsSelecting(false);
      setActiveAnnotation({ vehicle_type: '', vehicle_identifier: '', annotator_notes: '' });
    }
  };

  const cancelSelection = () => {
    setIsSelecting(false); setSelectionRange(null); setActiveAnnotation(null);
  };

  const handlePlayAudio = async () => {
    if (!selectionRange?.start || !selectionRange?.end) return;
    setIsPlaying(true);
    try {
      // --- THE FIX IS HERE ---
      // Ensure timestamps are always in the clean '...Z' format that FastAPI expects.
      const params = {
        collection: selectedCollection,
        start: new Date(selectionRange.start).toISOString(),
        end: new Date(selectionRange.end).toISOString(),
      };

      const response = await axios.get('/api/audio/raw', {
        params: params, // Use the cleaned params object
        responseType: 'arraybuffer',
      });

      const audioBlob = new Blob([response.data], { type: 'audio/wav' });
      const audioUrl = URL.createObjectURL(audioBlob);
      
      audioRef.current.src = audioUrl;
      audioRef.current.play();
      audioRef.current.onended = () => { setIsPlaying(false); URL.revokeObjectURL(audioUrl); };

    } catch (err) {
      setError('Failed to fetch or play audio clip.');
      setIsPlaying(false);
    }
  };

  const handleSaveAnnotation = async () => {
    if (!activeAnnotation.vehicle_type) {
        alert("Please select a vehicle type.");
        return;
    }
    const eventPayload = {
        ...activeAnnotation,
        start_timestamp: selectionRange.start,
        end_timestamp: selectionRange.end,
        direction: 'N/A'
    };
    try {
        const response = await axios.post('/api/events', eventPayload);
        setEvents(prev => [response.data, ...prev]);
        cancelSelection();
    } catch (err) { setError('Failed to save annotation.'); }
  };

  const handleNavigate = (direction) => {
    if (!startTime || !availableRange.start) return;
    const hopMs = durationSecs * 1000;
    let newStartMs = direction === 'next' ? startTime.getTime() + hopMs : startTime.getTime() - hopMs;
    const availableStartMs = availableRange.start.getTime();
    const availableEndMs = availableRange.end.getTime();
    if (newStartMs < availableStartMs) newStartMs = availableStartMs;
    if (newStartMs >= (availableEndMs - hopMs)) newStartMs = availableEndMs - hopMs;
    setStartTime(new Date(newStartMs));
  };
  
  const formatDateForInput = (date) => {
    if (!date) return '';
    const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return localDate.toISOString().slice(0, 19);
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
        <div className="time-controls-panel">
          <div className="control-group">
            <span className="control-label">Window:</span>
            <div className="button-tabs">{DURATION_OPTIONS.map(d => (<button key={d} className={`tab-button ${d === durationSecs ? 'selected' : ''}`} onClick={() => setDurationSecs(d)}>{d}s</button>))}</div>
          </div>
          <div className="control-group navigation-group">
            <button className="nav-button" onClick={() => handleNavigate('prev')}>{'<<'} Prev</button>
            <div className="start-time-input"><label htmlFor="start-time">Start Time:</label><input type="datetime-local" id="start-time" value={formatDateForInput(startTime)} onChange={(e) => setStartTime(new Date(e.target.value))} step="1"/></div>
            <button className="nav-button" onClick={() => handleNavigate('next')}>Next {'>>'}</button>
          </div>
          <div className="control-group"><label htmlFor="points-slider" className="control-label">Detail ({points} pts):</label><input type="range" id="points-slider" min="500" max="10000" step="100" value={points} onChange={(e) => setPoints(Number(e.target.value))} /></div>
        </div>
      )}

      {isLoading ? (
        <div style={{ height: '320px', display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#aaa' }}>Loading Chart Data...</div>
      ) : (
        <TimeSeriesChart chartData={chartData} onChartClick={handleChartClick} selection={selectionRange} />
      )}
      {isSelecting && <div className="selection-prompt">Click a second point on the chart to finish selection... (or <button className="link-button" onClick={cancelSelection}>Cancel</button>)</div>}

      {activeAnnotation && selectionRange && (
        <div className="annotation-form">
          <h4>New Annotation</h4>
          <p>Duration: {((new Date(selectionRange.end) - new Date(selectionRange.start))/1000).toFixed(2)}s</p>
          <select value={activeAnnotation.vehicle_type} onChange={e => setActiveAnnotation(p => ({...p, vehicle_type: e.target.value}))}>
            <option value="">-- Select Vehicle --</option>
            {vehicleConfigs.map(v => <option key={v.id} value={v.displayName}>{v.displayName}</option>)}
          </select>
          <input type="text" placeholder="Identifier (optional)" value={activeAnnotation.vehicle_identifier} onChange={e => setActiveAnnotation(p => ({...p, vehicle_identifier: e.target.value}))}/>
          <textarea placeholder="Notes..." value={activeAnnotation.annotator_notes} onChange={e => setActiveAnnotation(p => ({...p, annotator_notes: e.target.value}))}></textarea>
          <div className="form-actions">
            <button onClick={handlePlayAudio} disabled={isPlaying}>{isPlaying ? 'Playing...' : 'Play Audio'}</button>
            <button onClick={handleSaveAnnotation} className="save-button">Save Event</button>
            <button onClick={cancelSelection}>Cancel</button>
          </div>
        </div>
      )}

      <div className="event-log-container" style={{flex: '1', width: '100%', marginTop: '20px'}}>
        <EventLog events={events} onDeleteEvent={(id) => setEvents(p => p.filter(e => e.id !== id))} />
      </div>
    </div>
  );
}

export default AnnotationWorkspace;