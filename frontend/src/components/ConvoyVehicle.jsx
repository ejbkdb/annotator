// frontend/src/components/ConvoyVehicle.jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const WORKFLOW_STATE = { READY: 'READY', CAPTURING: 'CAPTURING', COMPLETE: 'COMPLETE' };
const VEHICLE_ACTIONS = ['driveby', 'rev', 'idle', 'flying', 'hover', 'na'];

function ConvoyVehicle({ tempId, convoyId, vehicleConfigs, onRemove, onEventSaved, setBackendStatus, convoyDirection, convoyNotes }) {
  const [workflow, setWorkflow] = useState(WORKFLOW_STATE.READY);
  const [startTime, setStartTime] = useState(null);
  const [endTime, setEndTime] = useState(null);
  const [timer, setTimer] = useState(0);
  const [vehicleData, setVehicleData] = useState({
    vehicle_type: vehicleConfigs[0]?.id || '',
    vehicle_action: VEHICLE_ACTIONS[0]
  });

  // Timer effect
  useEffect(() => {
    let interval;
    if (workflow === WORKFLOW_STATE.CAPTURING) {
      interval = setInterval(() => {
        setTimer(Math.floor((new Date() - startTime) / 1000));
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [workflow, startTime]);

  const handleStart = () => {
    setWorkflow(WORKFLOW_STATE.CAPTURING);
    setStartTime(new Date());
    setTimer(0);
  };

  const handleEnd = async () => {
    const finalEndTime = new Date();
    setEndTime(finalEndTime);
    setWorkflow(WORKFLOW_STATE.COMPLETE);

    const eventPayload = {
      ...vehicleData,
      start_timestamp: startTime.toISOString(),
      end_timestamp: finalEndTime.toISOString(),
      convoy_id: convoyId,
      direction: convoyDirection,
      annotator_notes: convoyNotes,
      vehicle_identifier: null,
    };

    try {
      const response = await axios.post('/api/events', eventPayload);
      onEventSaved(response.data);
      setBackendStatus('connected');
    } catch (error) {
      console.error(`Failed to save event for vehicle ${vehicleData.vehicle_type}:`, error);
      setBackendStatus('disconnected');
      alert(`Failed to save event for ${vehicleData.vehicle_type}: ${error.message}`);
      setWorkflow(WORKFLOW_STATE.CAPTURING);
      setEndTime(null);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setVehicleData(prev => ({ ...prev, [name]: value }));
  };

  const setVehicleAction = (action) => {
    setVehicleData(prev => ({ ...prev, vehicle_action: action }));
  };

  const getDuration = () => {
    if (!startTime || !endTime) return '00:00:00';
    return new Date(endTime - startTime).toISOString().substr(11, 8);
  };

  return (
    <div className="convoy-vehicle-card">
      <div className="convoy-vehicle-header">
        <select name="vehicle_type" value={vehicleData.vehicle_type} onChange={handleInputChange} disabled={workflow !== WORKFLOW_STATE.READY}>
          {vehicleConfigs.map(vc => <option key={vc.id} value={vc.id}>{vc.displayName}</option>)}
        </select>
        <button type="button" className="remove-vehicle-button" onClick={() => onRemove(tempId)}>✕</button>
      </div>
      <div className="convoy-vehicle-body">
        <div className="form-section vehicle-action-group">
            <label>Action:</label>
            <div className="button-group">
                {VEHICLE_ACTIONS.map(action => (
                    <button 
                        type="button" // FIX: Added type
                        key={action}
                        className={vehicleData.vehicle_action === action ? 'selected' : ''}
                        onClick={() => setVehicleAction(action)}
                        disabled={workflow !== WORKFLOW_STATE.READY}
                    >
                        {action.charAt(0).toUpperCase() + action.slice(1)}
                    </button>
                ))}
            </div>
        </div>
        <div className="timer-display small">
          Duration: {workflow === WORKFLOW_STATE.CAPTURING ? new Date(timer * 1000).toISOString().substr(11, 8) : getDuration()}
        </div>
        <div className="button-group">
          {workflow === WORKFLOW_STATE.READY && <button onClick={handleStart} className="start-button small">Start</button>}
          {workflow === WORKFLOW_STATE.CAPTURING && <button onClick={handleEnd} className="end-button small">Stop</button>}
          {workflow === WORKFLOW_STATE.COMPLETE && <span className="status-complete">✔️ Saved</span>}
        </div>
      </div>
    </div>
  );
}

export default ConvoyVehicle;