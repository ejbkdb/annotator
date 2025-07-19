// frontend/src/components/ReviewTab.jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './ReviewTab.css';

function ReviewTab({ onJumpTo }) {
  const [manualEvents, setManualEvents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchManualEvents = async () => {
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
  };

  useEffect(() => {
    const interval = setInterval(() => {
        fetchManualEvents();
    }, 5000);
    fetchManualEvents();
    return () => clearInterval(interval);
  }, []);

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

  if (isLoading && manualEvents.length === 0) return <div>Loading events for review...</div>;
  if (error) return <div style={{ color: 'red' }}>{error}</div>;

  return (
    <div className="review-container">
      <h2>Manual Events for Review ({manualEvents.length})</h2>
      <p>These are rough annotations captured in real-time. Click 'Review' to jump to the relevant time window in the file-based tool to create a precise annotation. The list auto-refreshes.</p>
      
      <div className="review-list">
        {manualEvents.length === 0 ? (
          <p>No manual events are pending review.</p>
        ) : (
          manualEvents.map(event => (
            <div key={event.id} className="review-item">
              <div className="review-item-details">
                <strong>{event.vehicle_type}</strong>
                <span>{new Date(event.start_timestamp).toLocaleString()}</span>
                <span>Duration: {((new Date(event.end_timestamp) - new Date(event.start_timestamp))/1000).toFixed(1)}s</span>
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