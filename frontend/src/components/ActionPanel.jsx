// frontend/src/components/ActionPanel.jsx
import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const WORKFLOW_STATE = { READY: 'READY', CAPTURING: 'CAPTURING', ANNOTATING: 'ANNOTATING' };
// --- Standardized Lists ---
const VEHICLE_ACTIONS = ['driveby', 'rev', 'idle', 'flying', 'hover', 'na'];
const DIRECTIONS = ['towards 103', 'towards de', 'clockwise', 'counterclockwise', 'na'];

const defaultFormState = {
  vehicleType: '',
  otherVehicleType: '',
  direction: DIRECTIONS[0],
  vehicle_action: VEHICLE_ACTIONS[0],
  notes: ''
};

function ActionPanel({ vehicleConfigs, onEventSaved, setBackendStatus }) {
  const [workflowState, setWorkflowState] = useState(WORKFLOW_STATE.READY);
  const [startTime, setStartTime] = useState(null);
  const [endTime, setEndTime] = useState(null);
  const [timer, setTimer] = useState(0);
  const [formData, setFormData] = useState(defaultFormState);

  useEffect(() => {
    let interval;
    if (workflowState === WORKFLOW_STATE.CAPTURING) {
      interval = setInterval(() => setTimer(Math.floor((new Date() - startTime) / 1000)), 1000);
    }
    return () => clearInterval(interval);
  }, [workflowState, startTime]);

  const resetAll = useCallback(() => {
    setWorkflowState(WORKFLOW_STATE.READY);
    setStartTime(null);
    setEndTime(null);
    setTimer(0);
    setFormData(defaultFormState);
  }, []);

  const handleStart = () => {
    setStartTime(new Date());
    setWorkflowState(WORKFLOW_STATE.CAPTURING);
  };
  const handleEnd = () => {
    setEndTime(new Date());
    setWorkflowState(WORKFLOW_STATE.ANNOTATING);
  };
  const handleCancel = () => {
    resetAll();
  };

  const handleSave = async () => {
    const finalVehicleType = formData.vehicleType === 'other' ? formData.otherVehicleType : formData.vehicleType;
    if (!finalVehicleType) return alert('Please select a vehicle type.');

    const eventPayload = {
      start_timestamp: startTime.toISOString(),
      end_timestamp: endTime.toISOString(),
      vehicle_type: finalVehicleType,
      vehicle_identifier: null, // Identifier is no longer used
      direction: formData.direction,
      annotator_notes: formData.notes,
      vehicle_action: formData.vehicle_action,
    };
    try {
      const response = await axios.post('/api/events', eventPayload);
      onEventSaved(response.data);
      setBackendStatus('connected');
      resetAll();
    } catch (error) {
      console.error('Failed to save event:', error);
      setBackendStatus('disconnected');
      alert(`Failed to save event: ${error.message}`);
    }
  };

  const handleInputChange = useCallback((e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  }, []);

  const renderContent = () => {
    switch (workflowState) {
      case WORKFLOW_STATE.CAPTURING:
        return (
          <>
            <div className="timer-display">{new Date(timer * 1000).toISOString().substr(11, 8)}</div>
            <button onClick={handleEnd} className="action-button end-button">MARK END</button>
          </>
        );
      case WORKFLOW_STATE.ANNOTATING:
        return (
          <div className="form-container">
            <h3>Total Duration: {new Date(endTime - startTime).toISOString().substr(11, 8)}</h3>
            <div className="form-section">
              <label>Vehicle Type*:</label>
              <div className="button-group" style={{ justifyContent: 'flex-start' }}>
                {vehicleConfigs.map(config => (
                  <button
                    type="button" // FIX: Added type
                    key={config.id}
                    className={formData.vehicleType === config.id ? 'selected' : ''}
                    onClick={() => setFormData(prev => ({ ...prev, vehicleType: config.id }))}
                  >
                    {config.displayName}
                  </button>
                ))}
              </div>
              {formData.vehicleType === 'other' && (
                <input
                  type="text"
                  name="otherVehicleType"
                  placeholder="Specify vehicle type"
                  value={formData.otherVehicleType}
                  onChange={handleInputChange}
                  style={{ marginTop: '10px' }}
                  autoFocus
                />
              )}
            </div>
            <div className="form-section">
              <label>Action:</label>
              <div className="button-group" style={{ justifyContent: 'flex-start' }}>
                {VEHICLE_ACTIONS.map(action => (
                    <button 
                        type="button" // FIX: Added type
                        key={action}
                        className={formData.vehicle_action === action ? 'selected' : ''}
                        onClick={() => setFormData(prev => ({...prev, vehicle_action: action}))}
                    >
                        {action.charAt(0).toUpperCase() + action.slice(1)}
                    </button>
                ))}
              </div>
            </div>
            <div className="form-section">
              <label>Direction:</label>
              <select name="direction" value={formData.direction} onChange={handleInputChange}>
                {DIRECTIONS.map(dir => <option key={dir} value={dir}>{dir}</option>)}
              </select>
            </div>
            <div className="form-section">
              <label>Notes:</label>
              <textarea name="notes" value={formData.notes} onChange={handleInputChange}></textarea>
            </div>
            <div className="button-pair">
              <button onClick={handleSave} className="save-button">SAVE EVENT</button>
              <button onClick={handleCancel} className="cancel-button">CANCEL</button>
            </div>
          </div>
        );
      default:
        return <button onClick={handleStart} className="action-button start-button">MARK START</button>;
    }
  };
  return renderContent();
}
export default ActionPanel;