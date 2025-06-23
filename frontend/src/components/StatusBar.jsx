// frontend/src/components/StatusBar.jsx
import React from 'react';

function StatusBar({ status, eventCount, lastSaveTime }) {
  const isConnected = status === 'connected';

  // Helper function to format the last save time into a local/UTC string
  const formatLastSaveTime = () => {
    if (!lastSaveTime) {
      return 'N/A';
    }
    const date = new Date(lastSaveTime);

    const localTimeStr = date.toLocaleTimeString();
    const utcTimeStr = date.toLocaleTimeString('en-GB', {
      timeZone: 'UTC',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    
    return `${localTimeStr} / ${utcTimeStr} UTC`;
  };

  return (
    <div className="status-bar">
      <div className="status-indicator">
        <div className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}></div>
        <span>{isConnected ? 'Connected to Backend' : 'Disconnected'}</span>
      </div>
      <span>Events Logged: {eventCount}</span>
      {/* --- UPDATED TIMESTAMP DISPLAY --- */}
      <span>Last Save: {formatLastSaveTime()}</span>
    </div>
  );
}

export default StatusBar;
// frontend/src/components/StatusBar.jsx