// frontend/src/App.jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import ActionPanel from './components/ActionPanel.jsx';
import EventLog from './components/EventLog.jsx';
import StatusBar from './components/StatusBar.jsx';

function App() {
  const [events, setEvents] = useState([]);
  const [vehicleConfigs, setVehicleConfigs] = useState([]);
  const [backendStatus, setBackendStatus] = useState('disconnected');
  const [lastSaveTime, setLastSaveTime] = useState(null);

  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        // Use Promise.all to fetch in parallel
        const [configRes, eventsRes, healthRes] = await Promise.all([
          axios.get('/api/config/vehicles'),
          axios.get('/api/events'),
          axios.get('/api/health')
        ]);

        if (healthRes.status === 200) setBackendStatus('connected');
        setVehicleConfigs(configRes.data);
        setEvents(eventsRes.data);
      } catch (error) {
        console.error("Failed to fetch initial data:", error);
        setBackendStatus('disconnected');
      }
    };
    fetchInitialData();
  }, []);

  const handleEventSaved = (newEvent) => {
    // Add new event to the top of the list
    setEvents(prevEvents => [newEvent, ...prevEvents]);
    setLastSaveTime(newEvent.end_timestamp);
  };

  const handleDeleteEvent = async (eventId) => {
    if (!window.confirm('Are you sure you want to delete this event?')) {
      return;
    }
    try {
      await axios.delete(`/api/events/${eventId}`);
      setEvents(prevEvents => prevEvents.filter(event => event.id !== eventId));
      setBackendStatus('connected');
    } catch (error) {
      console.error(`Failed to delete event ${eventId}:`, error);
      setBackendStatus('disconnected');
      alert(`Failed to delete event: ${error.message || 'Server error'}`);
    }
  };

  return (
    <div className="main-container">
      <header className="header"><h1>Test Range Annotation Tool</h1></header>
      <div className="content-container">
        <div className="action-panel-container">
          <ActionPanel vehicleConfigs={vehicleConfigs} onEventSaved={handleEventSaved} setBackendStatus={setBackendStatus} />
        </div>
        <div className="event-log-container">
          <EventLog events={events} onDeleteEvent={handleDeleteEvent} />
        </div>
      </div>
      <div className="status-bar-container">
        <StatusBar status={backendStatus} eventCount={events.length} lastSaveTime={lastSaveTime} />
      </div>
    </div>
  );
}
export default App;
// frontend/src/App.jsx