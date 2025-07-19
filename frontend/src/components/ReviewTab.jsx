// frontend/src/components/ReviewTab.jsx
import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import './ReviewTab.css';

function ReviewTab({ onJumpTo }) {
  const [manualEvents, setManualEvents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  // --- NEW: State to manage the sort order ---
  const [sortOrder, setSortOrder] = useState('desc'); // 'desc' for newest first, 'asc' for oldest first

  const fetchManualEvents = async () => {
    try {
      setIsLoading(true);
      setError('');
      // The backend already sends data sorted descending by default
      const response = await axios.get('/api/events?status=manual');
      setManualEvents(response.data);
    } catch (err) {
      setError('Failed to fetch manual events.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const interval = setInterval(() => {
        fetchManualEvents();
    }, 5000);
    fetchManualEvents();
    return () => clearInterval(interval);
  }, []);

  // --- NEW: Memoized sorting logic ---
  // This efficiently re-sorts the list only when the data or sort order changes.
  const sortedEvents = useMemo(() => {
    return [...manualEvents].sort((a, b) => {
      const dateA = new Date(a.start_timestamp);
      const dateB = new Date(b.start_timestamp);
      if (sortOrder === 'asc') {
        return dateA - dateB; // For ascending, oldest first
      }
      return dateB - dateA; // For descending, newest first
    });
  }, [manualEvents, sortOrder]);

  const handleReviewClick = async (event) => {
    try {
      const response = await axios.get(`/api/events/${event.id}/suggest-collection`);
      const { suggested_collection } = response.data;

      if (!suggested_collection) {
        alert(`Could not find a data collection containing the timestamp: ${event.start_timestamp}`);
        return;
      }
      
      const paddingSecs = 10;
      const eventDuration = (new Date(event.end_timestamp) - new Date(event.start_timestamp)) / 1000;
      const windowDuration = Math.max(20, eventDuration + paddingSecs);
      const startTime = new Date(new Date(event.start_timestamp).getTime() - (paddingSecs / 2) * 1000);

      onJumpTo({
        collection: suggested_collection,
        startTime: startTime,
        durationSecs: windowDuration,
        sourceEvent: event
      });

    } catch (err) {
      alert('An error occurred while trying to find the collection.');
      console.error(err);
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
        <h2>Manual Events for Review ({manualEvents.length})</h2>
        {/* --- NEW: Sort toggle button --- */}
        <button 
          className="sort-button"
          onClick={() => setSortOrder(current => current === 'desc' ? 'asc' : 'desc')}
        >
          Sort by Start Time: {sortOrder === 'desc' ? 'Newest First' : 'Oldest First'}
        </button>
      </div>
      <p>These are rough annotations captured in real-time. Click 'Review' to jump to the relevant time window in the file-based tool to create a precise annotation. The list auto-refreshes.</p>
      
      <div className="review-list">
        {manualEvents.length === 0 ? (
          <p>No manual events are pending review.</p>
        ) : (
          // --- MODIFIED: Map over the newly sorted array ---
          sortedEvents.map(event => (
            <div key={event.id} className="review-item">
              <div className="review-item-details">
                <div className="detail-row">
                    <span className="detail-label">Vehicle Type:</span>
                    <span className="detail-value type">{event.vehicle_type}</span>
                </div>
                <div className="detail-row">
                    <span className="detail-label">Identifier:</span>
                    <span className="detail-value">{event.vehicle_identifier || 'N/A'}</span>
                </div>
                <div className="detail-row">
                    <span className="detail-label">Start Time:</span>
                    <span className="detail-value">{formatTimestamp(event.start_timestamp)}</span>
                </div>
                <div className="detail-row">
                    <span className="detail-label">End Time:</span>
                    <span className="detail-value">{formatTimestamp(event.end_timestamp)}</span>
                </div>
                <div className="detail-row">
                    <span className="detail-label">Duration:</span>
                    <span className="detail-value">{((new Date(event.end_timestamp) - new Date(event.start_timestamp))/1000).toFixed(1)}s</span>
                </div>
              </div>
              <button onClick={() => handleReviewClick(event)} className="review-button">
                Review
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default ReviewTab;