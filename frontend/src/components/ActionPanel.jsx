// frontend/src/components/ActionPanel.jsx
import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const WORKFLOW_STATE = { READY: 'READY', CAPTURING: 'CAPTURING', ANNOTATING: 'ANNOTATING' };
const defaultFormState = { vehicleType: '', otherVehicleType: '', identifier: '', direction: 'N/A', notes: '' };

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
    setWorkflowState(WORKFLOW_STATE.READY); setStartTime(null); setEndTime(null);
    setTimer(0); setFormData(defaultFormState);
  }, []);

  const handleStart = () => { setStartTime(new Date()); setWorkflowState(WORKFLOW_STATE.CAPTURING); };
  const handleEnd = () => { setEndTime(new Date()); setWorkflowState(WORKFLOW_STATE.ANNOTATING); };
  const handleCancel = () => { resetAll(); };

  const handleSave = async () => {
    const finalVehicleType = formData.vehicleType === 'other' ? formData.otherVehicleType : formData.vehicleType;
    if (!finalVehicleType) return alert('Please select a vehicle type.');

    const eventPayload = {
      start_timestamp: startTime.toISOString(), end_timestamp: endTime.toISOString(),
      vehicle_type: finalVehicleType, vehicle_identifier: formData.identifier,
      direction: formData.direction, annotator_notes: formData.notes,
    };
    try {
      const response = await axios.post('/api/events', eventPayload);
      onEventSaved(response.data); setBackendStatus('connected'); resetAll();
    } catch (error) {
      console.error('Failed to save event:', error); setBackendStatus('disconnected');
      alert(`Failed to save event: ${error.message}`);
    }
  };

  const handleInputChange = (e) => setFormData(prev => ({ ...prev, [e.target.name]: e.target.value }));

  const renderContent = () => {
    switch (workflowState) {
      case WORKFLOW_STATE.CAPTURING:
        return <>
          <div className="timer-display">{new Date(timer * 1000).toISOString().substr(11, 8)}</div>
          <button onClick={handleEnd} className="action-button end-button">MARK END</button>
        </>;
      case WORKFLOW_STATE.ANNOTATING:
        return (
          <div className="form-container">
            <h3>Total Duration: {new Date(endTime - startTime).toISOString().substr(11, 8)}</h3>
            <div className="form-section">
              <label>Vehicle Type*:</label>
              <div className="button-group">
                {vehicleConfigs.map(config => <button key={config.id} className={formData.vehicleType === config.id ? 'selected' : ''} onClick={() => setFormData(prev => ({ ...prev, vehicleType: config.id }))}>{config.displayName}</button>)}
              </div>
              {formData.vehicleType === 'other' && <input type="text" name="otherVehicleType" placeholder="Specify vehicle type" value={formData.otherVehicleType} onChange={handleInputChange} style={{ marginTop: '10px' }} autoFocus />}
            </div>
            <div className="form-section"><label>Identifier:</label><input type="text" name="identifier" value={formData.identifier} onChange={handleInputChange} /></div>
            <div className="form-section"><label>Direction:</label><select name="direction" value={formData.direction} onChange={handleInputChange}><option value="N/A">N/A</option><option value="East -> West">East to West</option><option value="West -> East">West to East</option><option value="North -> South">North to South</option><option value="South -> North">South to North</option></select></div>
            <div className="form-section"><label>Notes:</label><textarea name="notes" value={formData.notes} onChange={handleInputChange}></textarea></div>
            <div className="button-pair"><button onClick={handleSave} className="save-button">SAVE EVENT</button><button onClick={handleCancel} className="cancel-button">CANCEL</button></div>
          </div>
        );
      default:
        return <button onClick={handleStart} className="action-button start-button">MARK START</button>;
    }
  };
  return renderContent();
}
export default ActionPanel;
// frontend/src/components/ActionPanel.jsx