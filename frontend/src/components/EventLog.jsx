// frontend/src/components/EventLog.jsx
import React from 'react';

// --- MODIFIED: Added onDeleteAnnotation to props ---
function EventLog({ events, onDeleteEvent, onDeleteAnnotation }) {
  if (!events || events.length === 0) {
    const message = onDeleteEvent ? "No events logged yet." : "No refined annotations created for this session.";
    return <h2>{message}</h2>;
  }

  const formatTimestamp = (isoString) => {
    if (!isoString) return { local: 'N/A', utc: 'N/A' };
    const date = new Date(isoString);
    const localTimeStr = date.toLocaleTimeString();
    const utcTimeStr = date.toLocaleTimeString('en-GB', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    return { local: localTimeStr, utc: utcTimeStr };
  };

  return (
    <div>
      <h2>{onDeleteEvent ? 'Real-time Event Log' : 'Refined Annotations'}</h2>
      <ul className="event-log-list">
        {events.map((event) => {
          const times = formatTimestamp(event.start_timestamp);
          const isRefined = 'parent_event_id' in event;
          
          return (
            <li key={event.id} className="event-log-item">
              <div className="event-log-item-header">
                <span>{String(event.vehicle_type).toUpperCase()}</span>
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <span className="timestamp-display">
                    {times.local} (Local) / {times.utc} (UTC)
                  </span>
                  {/* --- MODIFIED: Added logic for annotation deletion button --- */}
                  {onDeleteEvent && !isRefined && (
                    <button onClick={() => onDeleteEvent(event.id)} className="delete-event-button" title="Delete event">×</button>
                  )}
                  {onDeleteAnnotation && isRefined && (
                     <button onClick={() => onDeleteAnnotation(event.id)} className="delete-event-button" title="Delete annotation">×</button>
                  )}
                </div>
              </div>
              <div className="event-log-item-details">
                {isRefined ? (
                  <>
                    <strong>Source:</strong> {event.source_collection || 'N/A'} | <strong>Location:</strong> {event.location || 'N/A'} | <strong>Action:</strong> {event.action || 'N/A'}<br/>
                    <strong>Direction:</strong> {event.direction || 'N/A'} | <strong>Subclass:</strong> {event.vehicle_subclass || 'N/A'} <br/>
                    <strong>Notes:</strong> {event.annotator_notes || 'None'}
                  </>
                ) : (
                  <>
                    <strong>ID:</strong> {event.vehicle_identifier || 'N/A'} <br />
                    <strong>Notes:</strong> {event.annotator_notes || 'None'}
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default EventLog;