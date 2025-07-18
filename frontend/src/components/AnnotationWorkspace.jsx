// frontend/src/components/AnnotationWorkspace.jsx

import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import TimeSeriesChart from './TimeSeriesChart';
import EventLog from './EventLog';
import './AnnotationWorkspace.css';

import { parseISOString, formatForInput } from '../utils/time';

const DURATION_OPTIONS = [5, 10, 20, 50, 100];

// --- MODIFIED: Removed props that are now managed by the parent ---
function AnnotationWorkspace({ collections, selectedCollection, setSelectedCollection, jumpToData, activeReviewEvent }) {
  const [events, setEvents] = useState([]);
  const [vehicleConfigs, setVehicleConfigs] = useState([]);
  const [availableRange, setAvailableRange] = useState({ start: null, end: null });
  const [error, setError] = useState('');
  
  const [startTime, setStartTime] = useState(null);
  const [durationSecs, setDurationSecs] = useState(10);
  const [points, setPoints] = useState(2000);

  const [chartData, setChartData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const [isSelecting, setIsSelecting] = useState(false);
  const [selectionRange, setSelectionRange] = useState(null);
  const [activeAnnotation, setActiveAnnotation] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef(new Audio());

  useEffect(() => {
    if (jumpToData) {
      setStartTime(jumpToData.startTime);
      setDurationSecs(jumpToData.durationSecs);
    }
  }, [jumpToData]);

  useEffect(() => {
    axios.get('/api/config/vehicles').then(res => setVehicleConfigs(res.data));
  }, []);

  useEffect(() => {
    if (!selectedCollection) {
      setStartTime(null); 
      setAvailableRange({ start: null, end: null }); 
      setChartData([]);
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
        if (!jumpToData) {
            setStartTime(startUTC);
        }
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
    const clickedDate = parseISOString(timestamp);

    if (!isSelecting) {
      setIsSelecting(true);
      setSelectionRange({ start: clickedDate, end: null });
      setActiveAnnotation(null);
    } else {
      let finalStart = selectionRange.start;
      let finalEnd = clickedDate;
      
      if (finalEnd < finalStart) {
        [finalStart, finalEnd] = [finalEnd, finalStart];
      }
      
      setSelectionRange({ start: finalStart, end: finalEnd });
      setIsSelecting(false);
      
      // --- MODIFIED: Always inherit from the active review event if it exists ---
      setActiveAnnotation({ 
          vehicle_type: activeReviewEvent?.vehicle_type || '', 
          vehicle_identifier: activeReviewEvent?.vehicle_identifier || '', 
          annotator_notes: activeReviewEvent?.annotator_notes || '' 
      });
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
        params: {
          collection: selectedCollection,
          start: selectionRange.start.toISOString(),
          end: selectionRange.end.toISOString(),
        },
        responseType: 'arraybuffer',
      });

      const audioBlob = new Blob([response.data], { type: 'audio/wav' });
      const audioUrl = URL.createObjectURL(audioBlob);
      
      audioRef.current.src = audioUrl;
      audioRef.current.play();
      audioRef.current.onended = () => { setIsPlaying(false); URL.revokeObjectURL(audioUrl); };

    } catch (err) {
      console.error('Audio playback error:', err);
      setError('Failed to fetch or play audio clip.');
      setIsPlaying(false);
    }
  };

  const handleSaveAnnotation = async () => {
    if (!activeAnnotation.vehicle_type) {
        alert("Please select a vehicle type.");
        return;
    }
    
    const vehicleConfig = vehicleConfigs.find(v => v.id === activeAnnotation.vehicle_type);
    const vehicleDisplayName = vehicleConfig ? vehicleConfig.displayName : activeAnnotation.vehicle_type;

    const eventPayload = {
        ...activeAnnotation,
        vehicle_type: vehicleDisplayName,
        start_timestamp: selectionRange.start.toISOString(),
        end_timestamp: selectionRange.end.toISOString(),
        direction: 'N/A',
        status: 'refined'
    };
    
    try {
        const response = await axios.post('/api/events', eventPayload);
        setEvents(prev => [response.data, ...prev]);
        
        // --- REMOVED: The logic to update status is now handled by the "Finish Review" button ---
        
        cancelSelection();
    } catch (err) { setError('Failed to save annotation.'); }
  };

  const handleNavigate = (direction) => {
    if (!startTime || !availableRange.start) return;
    
    const hopMs = durationSecs * 1000;
    const currentMs = startTime.getTime();
    let newMs = direction === 'next' ? currentMs - hopMs : currentMs - hopMs;
    
    const availableStartMs = availableRange.start.getTime();
    const availableEndMs = availableRange.end.getTime();
    
    if (newMs < availableStartMs) newMs = availableStartMs;
    if (newMs >= (availableEndMs - hopMs)) newMs = availableEndMs - hopMs;
    
    setStartTime(new Date(newMs));
  };

  const handleTimeInputChange = (e) => {
    const inputValue = e.target.value;
    if (!inputValue) return;
    
    const userDate = new Date(inputValue + 'Z');
    setStartTime(userDate);
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
            <div className="button-tabs">
              {DURATION_OPTIONS.map(d => (
                <button 
                  key={d} 
                  className={`tab-button ${d === durationSecs ? 'selected' : ''}`} 
                  onClick={() => setDurationSecs(d)}
                >
                  {d}s
                </button>
              ))}
            </div>
          </div>
          <div className="control-group navigation-group">
            <button className="nav-button" onClick={() => handleNavigate('prev')}>{'<<'} Prev</button>
            <div className="start-time-input">
              <label htmlFor="start-time">Start Time (UTC):</label>
              <input 
                type="datetime-local" 
                id="start-time" 
                value={formatForInput(startTime)} 
                onChange={handleTimeInputChange}
                step="1"
              />
            </div>
            <button className="nav-button" onClick={() => handleNavigate('next')}>Next {'>>'}</button>
          </div>
          <div className="control-group">
            <label htmlFor="points-slider" className="control-label">Detail ({points} pts):</label>
            <input 
              type="range" 
              id="points-slider" 
              min="500" 
              max="10000" 
              step="100" 
              value={points} 
              onChange={(e) => setPoints(Number(e.target.value))} 
            />
          </div>
        </div>
      )}

      {isLoading ? (
        <div style={{ height: '320px', display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#aaa' }}>
          Loading Chart Data...
        </div>
      ) : (
        <TimeSeriesChart 
          chartData={chartData} 
          onChartClick={handleChartClick} 
          selection={selectionRange} 
        />
      )}
      
      {isSelecting && (
        <div className="selection-prompt">
          Click a second point on the chart to finish selection... (or{' '}
          <button className="link-button" onClick={cancelSelection}>Cancel</button>)
        </div>
      )}

      {activeAnnotation && selectionRange && (
        <div className="annotation-form">
          <h4>New Annotation</h4>
          <p>
            Duration: {((selectionRange.end - selectionRange.start)/1000).toFixed(2)}s
          </p>
          <select 
            value={activeAnnotation.vehicle_type} 
            onChange={e => setActiveAnnotation(p => ({...p, vehicle_type: e.target.value}))}
          >
            <option value="">-- Select Vehicle --</option>
            {vehicleConfigs.map(v => <option key={v.id} value={v.id}>{v.displayName}</option>)}
          </select>
          <input 
            type="text" 
            placeholder="Identifier (optional)" 
            value={activeAnnotation.vehicle_identifier} 
            onChange={e => setActiveAnnotation(p => ({...p, vehicle_identifier: e.target.value}))}
          />
          <textarea 
            placeholder="Notes..." 
            value={activeAnnotation.annotator_notes} 
            onChange={e => setActiveAnnotation(p => ({...p, annotator_notes: e.target.value}))}
          />
          <div className="form-actions">
            <button onClick={handlePlayAudio} disabled={isPlaying}>
              {isPlaying ? 'Playing...' : 'Play Audio'}
            </button>
            <button onClick={handleSaveAnnotation} className="save-button">Save Event</button>
            <button onClick={cancelSelection}>Cancel</button>
          </div>
        </div>
      )}

      <div className="event-log-container" style={{flex: '1', width: '100%', marginTop: '20px'}}>
        <EventLog 
          events={events} 
          onDeleteEvent={(id) => setEvents(p => p.filter(e => e.id !== id))} 
        />
      </div>
    </div>
  );
}

export default AnnotationWorkspace;