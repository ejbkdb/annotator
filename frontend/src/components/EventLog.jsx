// frontend/src/components/EventLog.jsx
import React from 'react';

function EventLog({ events }) {
  if (!events || events.length === 0) {
    return <h2>No events logged yet.</h2>;
  }

  // Helper function to format a single ISO timestamp into both local and UTC strings
  const formatTimestamp = (isoString) => {
    if (!isoString) {
      return { local: 'N/A', utc: 'N/A' };
    }
    const date = new Date(isoString);
    
    // Get local time using the browser's default locale and timezone
    const localTimeStr = date.toLocaleTimeString();

    // Get UTC time, formatted consistently as HH:MM:SS
    const utcTimeStr = date.toLocaleTimeString('en-GB', {
      timeZone: 'UTC',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });

    return { local: localTimeStr, utc: utcTimeStr };
  };

  return (
    <div>
      <h2>Event Log</h2>
      <ul className="event-log-list">
        {events.map((event) => {
          const times = formatTimestamp(event.start_timestamp);
          return (
            <li key={event.id} className="event-log-item">
              <div className="event-log-item-header">
                <span>{event.vehicle_type.toUpperCase()}</span>
                {/* --- UPDATED TIMESTAMP DISPLAY --- */}
                <span className="timestamp-display">
                  {times.local} (Local) / {times.utc} (UTC)
                </span>
              </div>
              <div className="event-log-item-details">
                <strong>ID:</strong> {event.vehicle_identifier || 'N/A'} <br />
                <strong>Notes:</strong> {event.annotator_notes || 'None'}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default EventLog;
// frontend/src/components/EventLog.jsx