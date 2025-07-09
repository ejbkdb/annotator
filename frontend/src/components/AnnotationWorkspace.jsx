// frontend/src/components/AnnotationWorkspace.jsx (Updated with Chart.js integration)

import React, { useState, useEffect } from 'react';
import axios from 'axios';
// --- CHANGE #1: Import the new TimeSeriesChart instead of Waveform ---
import TimeSeriesChart from './TimeSeriesChart';
import EventLog from './EventLog';
import './AnnotationWorkspace.css'; 

const DURATION_OPTIONS = [5, 10, 20, 50, 100]; // in seconds

function AnnotationWorkspace({ collections, selectedCollection, setSelectedCollection }) {
  const [events, setEvents] = useState([]);
  const [availableRange, setAvailableRange] = useState({ start: null, end: null });
  const [error, setError] = useState('');

  const [startTime, setStartTime] = useState(null);
  const [durationSecs, setDurationSecs] = useState(10);
  const [points, setPoints] = useState(2000);

  // --- CHANGE #2: Add state to hold chart data and loading status ---
  const [chartData, setChartData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  // This function is perfect, no changes needed.
  const formatDateForInput = (date) => {
    if (!date) return '';
    const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return localDate.toISOString().slice(0, 19);
  };

  // This hook is perfect, no changes needed.
  useEffect(() => {
    if (!selectedCollection) {
      setStartTime(null);
      setAvailableRange({ start: null, end: null });
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

  // --- CHANGE #3: Add a new useEffect to fetch the waveform data ---
  // This hook runs whenever the user changes the view (time, duration, etc.)
  useEffect(() => {
    if (!selectedCollection || !startTime) {
      return;
    }

    const endTime = new Date(startTime.getTime() + durationSecs * 1000);
    const fetchWaveformData = async () => {
      setIsLoading(true);
      setError('');
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
        setError(errorMsg);
        setChartData([]);
      } finally {
        setIsLoading(false);
      }
    };

    fetchWaveformData();
  }, [selectedCollection, startTime, durationSecs, points]); // Re-fetches on any change

  // This navigation logic is perfect, no changes needed.
  const handleNavigate = (direction) => {
    if (!startTime || !availableRange.start) return;
    const hopMs = durationSecs * 1000;
    
    let newStartMs = direction === 'next' 
      ? startTime.getTime() + hopMs 
      : startTime.getTime() - hopMs;

    const availableStartMs = availableRange.start.getTime();
    const availableEndMs = availableRange.end.getTime();
    
    if (newStartMs < availableStartMs) {
      newStartMs = availableStartMs;
    }
    if (newStartMs >= (availableEndMs - hopMs)) {
        newStartMs = availableEndMs - hopMs;
    }

    setStartTime(new Date(newStartMs));
  };

  const endTime = startTime ? new Date(startTime.getTime() + durationSecs * 1000) : null;

  // The entire return/JSX block is unchanged, except for the Waveform component replacement
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
              {DURATION_OPTIONS.map(duration => (
                <button
                  key={duration}
                  className={`tab-button ${duration === durationSecs ? 'selected' : ''}`}
                  onClick={() => setDurationSecs(duration)}
                >
                  {duration}s
                </button>
              ))}
            </div>
          </div>

          <div className="control-group navigation-group">
            <button className="nav-button" onClick={() => handleNavigate('prev')}>{'<<'} Prev</button>
            <div className="start-time-input">
              <label htmlFor="start-time">Start Time:</label>
              <input
                type="datetime-local"
                id="start-time"
                value={formatDateForInput(startTime)}
                onChange={(e) => setStartTime(new Date(e.target.value))}
                step="1"
              />
            </div>
            <button className="nav-button" onClick={() => handleNavigate('next')}>Next {'>>'}</button>
          </div>
          
          <div className="control-group">
            <label htmlFor="points-slider" className="control-label">Detail ({points} pts):</label>
            <input type="range" id="points-slider" min="500" max="10000" step="100" value={points} onChange={(e) => setPoints(Number(e.target.value))} />
          </div>

        </div>
      )}

      {/* --- CHANGE #4: Replace the Waveform component with the new TimeSeriesChart --- */}
      {isLoading ? (
        <div style={{ height: '320px', display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#aaa' }}>Loading Chart Data...</div>
      ) : (
        <TimeSeriesChart chartData={chartData} />
      )}
      
      <div className="event-log-container" style={{flex: '1', width: '100%', marginTop: '20px'}}>
        <EventLog events={events} onDeleteEvent={(id) => setEvents(p => p.filter(e => e.id !== id))} />
      </div>
    </div>
  );
}

export default AnnotationWorkspace;