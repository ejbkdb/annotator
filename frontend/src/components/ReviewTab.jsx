import React, { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import './ReviewTab.css';

function ReviewTab({ onJumpTo }) {
  const [manualEvents, setManualEvents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [sortOrder, setSortOrder] = useState('asc');

  const fetchManualEvents = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await axios.get('/api/events?status=manual');
      setManualEvents(response.data);
    } catch (err) {
      setError('Failed to fetch manual events.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchManualEvents();
    const interval = setInterval(fetchManualEvents, 10000);
    return () => clearInterval(interval);
  }, [fetchManualEvents]);

  const sortedEvents = useMemo(() => {
    return [...manualEvents].sort((a, b) => {
      const dateA = new Date(a.start_timestamp);
      const dateB = new Date(b.start_timestamp);
      return sortOrder === 'asc' ? dateA - dateB : dateB - a;
    });
  }, [manualEvents, sortOrder]);

  const handleReviewClick = async (event) => {
    try {
      const response = await axios.get(`/api/events/${event.id}/suggest-collection`);
      const { suggested_collection } = response.data;
      if (!suggested_collection) {
        return alert(`Could not find a data collection for timestamp: ${event.start_timestamp}`);
      }
      
      // Correctly calculate time range to restore functionality
      const paddingSecs = 10;
      const eventStart = new Date(event.start_timestamp);
      const eventEnd = new Date(event.end_timestamp);
      const eventDurationSecs = (eventEnd - eventStart) / 1000;
      const windowDuration = Math.max(20, eventDurationSecs + paddingSecs);
      const startTimeWithPadding = new Date(eventStart.getTime() - (paddingSecs / 2) * 1000);

      onJumpTo({ 
        collection: suggested_collection, 
        startTime: startTimeWithPadding, 
        durationSecs: windowDuration, 
        sourceEvent: event 
      });

    } catch (err) {
      alert('An error occurred while trying to find the collection.');
    }
  };
  
  const handleResetClick = async (eventId) => {
    if (!window.confirm("Are you sure? This will delete all refined clips and reset the event.")) return;
    try {
      await axios.post(`/api/events/${eventId}/reset`);
      fetchManualEvents();
    } catch (err) {
      alert(`Failed to reset event: ${err.response?.data?.detail || err.message}`);
    }
  };

  if (isLoading && manualEvents.length === 0) return <div>Loading events for review...</div>;
  if (error) return <div style={{ color: 'red' }}>{error}</div>;

  return (
    <div className="review-container">
      <div className="review-header">
        <h2>Manual Events Pending Review ({manualEvents.length})</h2>
        <button className="sort-button" onClick={() => setSortOrder(current => current === 'desc' ? 'asc' : 'desc')}>
          Sort: {sortOrder === 'desc' ? 'Newest First' : 'Oldest First'}
        </button>
      </div>
      <p>Click 'Review' to load the event and associated sensor data. The list auto-refreshes.</p>
      
      <div className="review-list">
        {sortedEvents.map(event => (
            <div key={event.id} className="review-item">
              <div className="review-item-details">
                <div className="detail-row"><span className="detail-label">Vehicle Type:</span><span className="detail-value type">{event.vehicle_type}</span></div>
                <div className="detail-row"><span className="detail-label">Start Time:</span><span className="detail-value">{new Date(event.start_timestamp).toLocaleString()}</span></div>
                <div className="detail-row"><span className="detail-label">Duration:</span><span className="detail-value">{((new Date(event.end_timestamp) - new Date(event.start_timestamp))/1000).toFixed(1)}s</span></div>
              </div>
              <div style={{display: "flex", gap: "10px"}}>
                <button onClick={() => handleResetClick(event.id)} className="review-button" style={{backgroundColor: '#6c757d'}}>Reset</button>
                <button onClick={() => handleReviewClick(event)} className="review-button">Review</button>
              </div>
            </div>
        ))}
      </div>
    </div>
  );
}

export default ReviewTab;