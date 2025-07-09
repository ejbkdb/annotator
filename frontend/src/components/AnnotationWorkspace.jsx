// frontend/src/components/AnnotationWorkspace.jsx

import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Waveform from './Waveform';
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

  const formatDateForInput = (date) => {
    if (!date) return '';
    const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return localDate.toISOString().slice(0, 19);
  };

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

      <Waveform
        collection={selectedCollection} 
        start={startTime ? startTime.toISOString() : ''} 
        end={endTime ? endTime.toISOString() : ''} 
        points={points} 
      />
      
      <div className="event-log-container" style={{flex: '1', width: '100%', marginTop: '20px'}}>
        <EventLog events={events} onDeleteEvent={(id) => setEvents(p => p.filter(e => e.id !== id))} />
      </div>
    </div>
  );
}

export default AnnotationWorkspace;
