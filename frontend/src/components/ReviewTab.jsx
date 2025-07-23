import React, { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import './ReviewTab.css';

function ReviewTab({ onJumpTo }) {
  const [manualEvents, setManualEvents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [sortOrder, setSortOrder] = useState('asc');

  const fetchManualEvents = useCallback(async () => {
    try {
      setIsLoading(true);
      setError('');
      const response = await axios.get('/api/events?status=manual');
      setManualEvents(response.data);
    } catch (err) {
      setError('Failed to fetch manual events.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const interval = setInterval(fetchManualEvents, 5000);
    fetchManualEvents();
    return () => clearInterval(interval);
  }, [fetchManualEvents]);

  const sortedEvents = useMemo(() => {
    return [...manualEvents].sort((a, b) => {
      const dateA = new Date(a.start_timestamp);
      const dateB = new Date(b.start_timestamp);
      return sortOrder === 'asc' ? dateA - dateB : dateB - dateA;
    });
  }, [manualEvents, sortOrder]);

  const handleReviewClick = async (event) => {
    try {
      // --- FIX: Corrected template literal string ---
      const response = await axios.get(`/api/events/${event.id}/suggest-collection`);
      const { suggested_collection } = response.data;

      if (!suggested_collection) {
        // --- FIX: Corrected alert syntax ---
        alert(`Could not find a data collection for timestamp: ${event.start_timestamp}`);
        return;
      }
      
      const paddingSecs = 10;
      const eventDuration = (new Date(event.end_timestamp) - new Date(event.start_timestamp)) / 1000;
      const windowDuration = Math.max(20, eventDuration + paddingSecs);
      const startTime = new Date(new Date(event.start_timestamp).getTime() - (paddingSecs / 2) * 1000);

      onJumpTo({ collection: suggested_collection, startTime, durationSecs: windowDuration, sourceEvent: event });

    } catch (err) {
      alert('An error occurred while trying to find the collection.');
      console.error(err);
    }
  };
  
  const handleResetClick = async (eventId) => {
    if (!window.confirm("Are you sure? This will delete all refined clips for this event and reset its status to 'manual' for re-annotation.")) {
      return;
    }
    try {
      // --- FIX: Corrected template literal string ---
      await axios.post(`/api/events/${eventId}/reset`);
      // --- FIX: Corrected alert syntax ---
      alert(`Event ${eventId} has been reset.`);
      // The list will auto-refresh via the interval, so we don't need to manually update state here.
    } catch (err) {
      // --- FIX: Corrected alert syntax ---
      alert(`Failed to reset event: ${err.response?.data?.detail || err.message}`);
    }
  };

  const formatTimestamp = (isoString) => {
      if (!isoString) return 'N/A';
      return new Date(isoString).toLocaleString();
  }

  if (isLoading && manualEvents.length === 0) return <div>Loading events for review...</div>;
  if (error) return <div style={{ color: 'red' }}>{error}</div>;

  return (
    <div className="review-container">
      <div className="review-header">
        <h2>Manual Events Pending Review ({manualEvents.length})</h2>
        <button 
          className="sort-button"
          onClick={() => setSortOrder(current => current === 'desc' ? 'asc' : 'desc')}
        >
          Sort: {sortOrder === 'desc' ? 'Newest First' : 'Oldest First'}
        </button>
      </div>
      <p>Click 'Review' to refine an annotation. 'Reset' will delete all children and set the parent back to manual. The list auto-refreshes.</p>
      
      <div className="review-list">
        {manualEvents.length === 0 ? (
          <p>No manual events are pending review.</p>
        ) : (
          sortedEvents.map(event => (
            <div key={event.id} className="review-item">
              <div className="review-item-details">
                <div className="detail-row"><span className="detail-label">Vehicle Type:</span><span className="detail-value type">{event.vehicle_type}</span></div>
                <div className="detail-row"><span className="detail-label">Identifier:</span><span className="detail-value">{event.vehicle_identifier || 'N/A'}</span></div>
                <div className="detail-row"><span className="detail-label">Start Time:</span><span className="detail-value">{formatTimestamp(event.start_timestamp)}</span></div>
                <div className="detail-row"><span className="detail-label">Duration:</span><span className="detail-value">{((new Date(event.end_timestamp) - new Date(event.start_timestamp))/1000).toFixed(1)}s</span></div>
              </div>
              <div style={{display: "flex", gap: "10px"}}>
                <button onClick={() => handleResetClick(event.id)} className="review-button" style={{backgroundColor: '#6c757d'}}>Reset</button>
                <button onClick={() => handleReviewClick(event)} className="review-button">Review</button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default ReviewTab;