// frontend/src/components/ConvoyBuilder.jsx
import React, { useState, useCallback, useEffect } from 'react';
import axios from 'axios';
import ConvoyVehicle from './ConvoyVehicle.jsx';

// --- Standardized List ---
const DIRECTIONS = ['towards 103', 'towards de', 'clockwise', 'counterclockwise'];

// Custom hook for debouncing (unchanged)
function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);
    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);
  return debouncedValue;
}

function ConvoyBuilder({ vehicleConfigs, onEventSaved, setBackendStatus }) {
  const [activeConvoy, setActiveConvoy] = useState(null);
  const [vehicles, setVehicles] = useState([]);
  const [convoyData, setConvoyData] = useState({
    convoy_number: '',
    convoy_spacing_seconds: '',
    direction: DIRECTIONS[0],
    notes: '',
  });

  const debouncedSpacing = useDebounce(convoyData.convoy_spacing_seconds, 500);
  const debouncedDirection = useDebounce(convoyData.direction, 500);
  const debouncedNotes = useDebounce(convoyData.notes, 500);

  useEffect(() => {
    if (!activeConvoy) return;
    const updateMetadata = async () => {
      try {
        const payload = {
          direction: debouncedDirection,
          notes: debouncedNotes,
          convoy_spacing_seconds: parseInt(debouncedSpacing, 10) || null,
        };
        await axios.put(`/api/convoys/${activeConvoy.id}`, payload);
        setBackendStatus('connected');
      } catch (error) {
        console.error("Failed to auto-update convoy metadata:", error);
        setBackendStatus('disconnected');
      }
    };
    updateMetadata();
  }, [activeConvoy, debouncedSpacing, debouncedDirection, debouncedNotes, setBackendStatus]);


  const handleGenerateConvoy = async () => {
    if (!convoyData.convoy_number) return alert('Please enter a Convoy Name / ID to begin.');
    try {
      const response = await axios.post('/api/convoys', {
        convoy_number: convoyData.convoy_number,
        direction: convoyData.direction,
        notes: convoyData.notes,
        convoy_spacing_seconds: parseInt(convoyData.convoy_spacing_seconds, 10) || null,
      });
      setActiveConvoy(response.data);
      setBackendStatus('connected');
    } catch (error) {
      console.error('Failed to generate convoy:', error);
      setBackendStatus('disconnected');
      alert(`Failed to generate convoy: ${error.response?.data?.detail || error.message}`);
    }
  };

  const handleFinishConvoy = () => {
    setActiveConvoy(null);
    setVehicles([]);
    setConvoyData({ convoy_number: '', convoy_spacing_seconds: '', direction: DIRECTIONS[0], notes: '' });
  };

  const addVehicle = () => {
    setVehicles(prev => [...prev, { tempId: `temp_${Date.now()}_${Math.random()}` }]);
  };

  const removeVehicle = (tempId) => {
    setVehicles(prev => prev.filter(v => v.tempId !== tempId));
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setConvoyData(prev => ({ ...prev, [name]: value }));
  };

  if (!activeConvoy) {
    return (
      <div className="convoy-builder-container">
        <div className="convoy-common-form">
          <h3>Start a New Convoy</h3>
          <div className="form-section">
            <label>Convoy Name / ID*:</label>
            <input type="text" name="convoy_number" value={convoyData.convoy_number} onChange={handleInputChange} placeholder="e.g., Test 1A, Alpha Group, etc."/>
          </div>
          <button onClick={handleGenerateConvoy} className="action-button start-button">Generate New Convoy</button>
        </div>
      </div>
    );
  }

  return (
    <div className="convoy-builder-container">
      <h2>Active Convoy: {activeConvoy.convoy_number}</h2>
      {vehicles.map(vehicle => (
        <ConvoyVehicle
          key={vehicle.tempId}
          tempId={vehicle.tempId}
          convoyId={activeConvoy.id}
          vehicleConfigs={vehicleConfigs}
          onRemove={removeVehicle}
          onEventSaved={onEventSaved}
          setBackendStatus={setBackendStatus}
          convoyDirection={convoyData.direction}
          convoyNotes={convoyData.notes}
        />
      ))}
      <button onClick={addVehicle} className="add-vehicle-button">+ Add Vehicle</button>
      
      <div className="convoy-common-form">
        <h3>Convoy Information</h3>
        <div className="form-section">
          <label>Convoy Spacing (seconds):</label>
          <input type="number" name="convoy_spacing_seconds" value={convoyData.convoy_spacing_seconds} onChange={handleInputChange} />
        </div>
        <div className="form-section">
          <label>Direction:</label>
          <select name="direction" value={convoyData.direction} onChange={handleInputChange}>
            {DIRECTIONS.map(dir => <option key={dir} value={dir}>{dir}</option>)}
          </select>
        </div>
        <div className="form-section">
          <label>General Notes:</label>
          <textarea name="notes" value={convoyData.notes} onChange={handleInputChange}></textarea>
        </div>
        <button onClick={handleFinishConvoy} className="cancel-button">Finish & Start New Convoy</button>
      </div>
    </div>
  );
}

export default ConvoyBuilder;