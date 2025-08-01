import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import TimeSeriesChart from './TimeSeriesChart';
import EventLog from './EventLog';
import SensorSelector from './SensorSelector';
import './AnnotationWorkspace.css';
import { parseISOString, formatForInput } from '../utils/time';

const DURATION_OPTIONS = [5, 10, 20, 50, 100];
const FIXED_WINDOW_OPTIONS = [5, 8, 10];
const defaultAnnotationState = { vehicle_type: '', location: 'tarmac', action: 'driveby', direction: 'na', annotator_notes: '' };

const generateSensorColor = (name) => {
    const colors = ['#61dafb', '#2a9d8f', '#e76f51', '#f4a261', '#e9c46a', '#264653', '#9b59b6', '#3498db', '#95a5a6', '#e67e22'];
    let hash = 0;
    for (let i = 0; i < name.length; i++) { hash = name.charCodeAt(i) + ((hash << 5) - hash); }
    return colors[Math.abs(hash) % colors.length];
};

const getSensorDisplayName = (id) => id.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

function AnnotationWorkspace({ 
  collections, selectedCollections, setSelectedCollections,
  sensorOrder, setSensorOrder, jumpToData, activeReviewEvent
}) {
  const [refinedAnnotations, setRefinedAnnotations] = useState([]);
  const [vehicleConfigs, setVehicleConfigs] = useState([]);
  const [chartData, setChartData] = useState({});
  const [selectionRange, setSelectionRange] = useState({});
  const [errors, setErrors] = useState({});
  const [startTime, setStartTime] = useState(null);
  const [durationSecs, setDurationSecs] = useState(10);
  const [isLoading, setIsLoading] = useState(false);
  const [selectionMode, setSelectionMode] = useState('manual');
  const [fixedWindowSize, setFixedWindowSize] = useState(8);
  const [isSelecting, setIsSelecting] = useState('');
  const [pendingAnnotations, setPendingAnnotations] = useState([]);

  const fetchRefinedAnnotations = useCallback(() => {
    if (activeReviewEvent?.id) {
        axios.get('/api/annotations/refined', { params: { parent_event_id: activeReviewEvent.id } })
             .then(res => setRefinedAnnotations(res.data))
             .catch(err => console.error("Could not fetch refined annotations", err));
    } else {
        setRefinedAnnotations([]);
    }
  }, [activeReviewEvent]);

  useEffect(() => {
    axios.get('/api/config/vehicles').then(res => setVehicleConfigs(res.data));
    fetchRefinedAnnotations();
  }, [fetchRefinedAnnotations]);
  
  useEffect(() => {
    if (jumpToData) {
        setStartTime(jumpToData.startTime);
        setDurationSecs(jumpToData.durationSecs);
        setSelectionRange({});
        setPendingAnnotations([]);
    }
  }, [jumpToData]);

  useEffect(() => {
    if (!selectedCollections.length || !startTime) {
        setChartData({});
        setErrors({});
        return;
    }
    const fetchAllWaveforms = async () => {
      setIsLoading(true);
      // CORRECTED: Explicitly clear previous state to prevent stale data.
      setChartData({});
      setErrors({});
      
      const endTime = new Date(startTime.getTime() + durationSecs * 1000);
      const promises = selectedCollections.map(c =>
        axios.get('/api/audio/waveform', { params: { collection: c, start: startTime.toISOString(), end: endTime.toISOString(), points: 2000 } })
             .then(res => ({ collection: c, data: res.data, error: null }))
             .catch(err => ({ collection: c, data: [], error: err.response?.data?.detail || 'Failed' }))
      );
      const results = await Promise.all(promises);
      const newChartData = {};
      const newErrors = {};
      results.forEach(result => {
        if (result.error) {
          newErrors[result.collection] = result.error;
        } else if (result.data?.length > 0) {
          newChartData[result.collection] = result.data;
        }
      });
      setChartData(newChartData);
      setErrors(newErrors);
      setIsLoading(false);
    };
    fetchAllWaveforms();
  }, [selectedCollections, startTime, durationSecs]);

  const addOrUpdateAnnotation = (sensorId, start, end) => {
    setSelectionRange(prev => ({ ...prev, [sensorId]: { start, end } }));
    const newAnnotation = { ...defaultAnnotationState, vehicle_type: activeReviewEvent?.vehicle_type || '', sensorId, start, end };
    setPendingAnnotations(prev => [...prev.filter(ann => ann.sensorId !== sensorId), newAnnotation]);
    setIsSelecting('');
  };

  const handleChartClick = (timestamp, sensorId) => {
    const clickedDate = parseISOString(timestamp);
    if (selectionMode === 'fixed') {
        const halfWindowMs = (Number(fixedWindowSize) * 1000) / 2;
        addOrUpdateAnnotation(sensorId, new Date(clickedDate.getTime() - halfWindowMs), new Date(clickedDate.getTime() + halfWindowMs));
    } else {
        if (isSelecting !== sensorId) {
            setIsSelecting(sensorId);
            setSelectionRange(prev => ({ ...prev, [sensorId]: { start: clickedDate, end: null } }));
        } else {
            const [start, end] = [selectionRange[sensorId].start, clickedDate].sort((a, b) => a - b);
            addOrUpdateAnnotation(sensorId, start, end);
        }
    }
  };

  const cancelAnnotation = (sensorId) => {
    setSelectionRange(prev => { const newState = {...prev}; delete newState[sensorId]; return newState; });
    setPendingAnnotations(prev => prev.filter(ann => ann.sensorId !== sensorId));
  };

  const handleAnnotationInputChange = (sensorId, field, value) => {
    setPendingAnnotations(prev => prev.map(ann => ann.sensorId === sensorId ? { ...ann, [field]: value } : ann));
  };
  
  const handleSaveAnnotation = async (sensorId) => {
    const annotation = pendingAnnotations.find(ann => ann.sensorId === sensorId);
    if (!annotation?.vehicle_type || !activeReviewEvent) return alert("Vehicle type and review session required.");

    const payload = { ...annotation, parent_event_id: activeReviewEvent.id, source_collection: sensorId, start_timestamp: annotation.start.toISOString(), end_timestamp: annotation.end.toISOString() };
    try {
        await axios.post('/api/annotations/refined', payload);
        fetchRefinedAnnotations();
        cancelAnnotation(sensorId);
    } catch (err) { alert(`Failed to save: ${err.response?.data?.detail || err.message}`); }
  };
  
  const handleNavigate = (direction) => {
    if (!startTime) return;
    setStartTime(new Date(startTime.getTime() + (direction === 'next' ? 1 : -1) * durationSecs * 1000));
  };
  
  // CORRECTED: Create a guaranteed unique and sorted list for rendering.
  const uniqueSortedSelectedCollections = useMemo(() => {
    const unique = Array.from(new Set(selectedCollections));
    return unique.sort((a, b) => sensorOrder.indexOf(a) - sensorOrder.indexOf(b));
  }, [selectedCollections, sensorOrder]);

  return (
    <div className="workspace-container">
      <SensorSelector allCollections={collections} selectedCollections={selectedCollections} setSelectedCollections={setSelectedCollections} sensorOrder={sensorOrder} setSensorOrder={setSensorOrder} />
      {selectedCollections.length > 0 && (
        <>
          <div className="time-controls-panel">
            <div className="control-group"><span className="control-label">Window:</span><div className="button-tabs">{DURATION_OPTIONS.map(d => <button key={d} className={`tab-button ${d === durationSecs ? 'selected' : ''}`} onClick={() => setDurationSecs(d)}>{d}s</button>)}</div></div>
            <div className="control-group"><button className="nav-button" onClick={() => handleNavigate('prev')}>{'<<'}</button><input type="datetime-local" value={formatForInput(startTime)} onChange={(e) => setStartTime(new Date(e.target.value + 'Z'))} step="1"/><button className="nav-button" onClick={() => handleNavigate('next')}>{'>>'}</button></div>
          </div>
          <div className="time-controls-panel" style={{justifyContent: "flex-start"}}>
            <div className="control-group"><span className="control-label">Selection:</span><div className="button-tabs"><button className={`tab-button ${selectionMode === 'manual' ? 'selected' : ''}`} onClick={() => setSelectionMode('manual')}>Manual</button><button className={`tab-button ${selectionMode === 'fixed' ? 'selected' : ''}`} onClick={() => setSelectionMode('fixed')}>Fixed</button></div></div>
            {selectionMode === 'fixed' && (<div className="control-group"><span className="control-label">Size:</span><div className="button-tabs">{FIXED_WINDOW_OPTIONS.map(d => <button key={d} className={`tab-button ${d === fixedWindowSize ? 'selected' : ''}`} onClick={() => setFixedWindowSize(d)}>{d}s</button>)}</div></div>)}
          </div>
        </>
      )}
      <div className="multi-sensor-view-scrollable">
        {isLoading ? <div className="loading-message">Loading Chart Data...</div> : uniqueSortedSelectedCollections.map(sensorId => {
            const pendingAnnotation = pendingAnnotations.find(ann => ann.sensorId === sensorId);
            return (
            <div key={sensorId} className="sensor-plot-container">
              <div className="sensor-header"><div className="sensor-title"><div className="sensor-color-dot" style={{ backgroundColor: generateSensorColor(sensorId) }}></div><h3>{getSensorDisplayName(sensorId)}</h3></div>{errors[sensorId] && <div className="sensor-error">⚠️ {errors[sensorId]}</div>}</div>
              {(chartData[sensorId] && chartData[sensorId].length > 0) ? (<TimeSeriesChart chartData={chartData[sensorId]} onChartClick={(ts) => handleChartClick(ts, sensorId)} selection={selectionRange[sensorId]} color={generateSensorColor(sensorId)} />) : <div className="no-data-message">{!errors[sensorId] && "No data available"}</div>}
              {pendingAnnotation && (
                <div className="sensor-annotation-form">
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px'}}>
                        <select value={pendingAnnotation.vehicle_type} onChange={(e) => handleAnnotationInputChange(sensorId, 'vehicle_type', e.target.value)}><option value="">-- Vehicle --</option>{vehicleConfigs.map(v => <option key={v.id} value={v.id}>{v.displayName}</option>)}</select>
                        <select value={pendingAnnotation.location} onChange={(e) => handleAnnotationInputChange(sensorId, 'location', e.target.value)}><option value="tarmac">Tarmac</option><option value="fastpass">Fastpass</option><option value="jungle">Jungle</option></select>
                        <select value={pendingAnnotation.action} onChange={(e) => handleAnnotationInputChange(sensorId, 'action', e.target.value)}><option value="driveby">Driveby</option><option value="rev">Rev</option><option value="idle">Idle</option><option value="flying">Flying</option><option value="hover">Hover</option></select>
                        <select value={pendingAnnotation.direction} onChange={(e) => handleAnnotationInputChange(sensorId, 'direction', e.target.value)}><option value="towards_de">Towards DE</option><option value="towards_103">Towards 103</option><option value="na">N/A</option></select>
                    </div>
                    <textarea placeholder="Notes..." value={pendingAnnotation.annotator_notes} onChange={(e) => handleAnnotationInputChange(sensorId, 'annotator_notes', e.target.value)}/>
                    <div className="form-actions"><button onClick={() => handleSaveAnnotation(sensorId)} className="save-button">Save</button><button onClick={() => cancelAnnotation(sensorId)}>Cancel</button></div>
                </div>
              )}
            </div>
            )
        })}
      </div>
      {isSelecting && <div className="selection-prompt">Click a second point on the <strong>{getSensorDisplayName(isSelecting)}</strong> chart... (or <button className="link-button" onClick={() => setIsSelecting('')}>Cancel</button>)</div>}
      <div className="event-log-container"><EventLog events={refinedAnnotations} onDeleteAnnotation={(id) => { if(window.confirm("Delete?")) { axios.delete(`/api/annotations/refined/${id}`).then(fetchRefinedAnnotations); }}} /></div>
    </div>
  );
}

export default AnnotationWorkspace;