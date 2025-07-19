// frontend/src/components/ReviewSessionControls.jsx
import React from 'react';
import './ReviewSessionControls.css';

function ReviewSessionControls({ sourceEvent, onEndReview }) {
  if (!sourceEvent) return null;

  return (
    <div className="review-session-banner">
      <div className="review-session-info">
        <span>Reviewing:</span>
        <strong>{sourceEvent.vehicle_type}</strong>
        <span>from {new Date(sourceEvent.start_timestamp).toLocaleString()}</span>
      </div>
      <div className="review-session-instructions">
        Create one or more refined annotations below. Click "Finish Review" when done.
      </div>
      <button onClick={onEndReview} className="end-review-button">
        Finish Review & Mark as Complete
      </button>
    </div>
  );
}

export default ReviewSessionControls;