import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import TimeSeriesChart from './TimeSeriesChart';
import EventLog from './EventLog';
import SensorSelector from './SensorSelector';
import './AnnotationWorkspace.css';
import { parseISOString, formatForInput } from '../utils/time';

const DURATION_OPTIONS = [5, 10, 20, 50, 100];
const FIXED_WINDOW_OPTIONS = [5, 8, 10, 15, 12];
const defaultAnnotationState = { vehicle_type: '', location: 'fastpass', action: 'driveby', direction: 'na', annotator_notes: '' };

const generateSensorColor = (name) => {
    const colors = ['#61dafb', '#2a9d8f', '#e76f51', '#f4a261', '#e9c46a', '#264653', '#9b59b6', '#3498db', '#95a5a6', '#e67e22'];
    let hash = 0;
    for (let i = 0; i < name.length; i++) { hash = name.charCodeAt(i) + ((hash << 5) - hash); }
    return colors[Math.abs(hash) % colors.length];
};

const getSensorDisplayName = (id) => id.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());


function AnnotationWorkspace({ 
  collections, selectedCollections, setSelectedCollections,
  sensorOrder, setSensorOrder, jumpToData, activeReviewEvent, onEndReview
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
  const [globalAnnotation, setGlobalAnnotation] = useState(defaultAnnotationState);
  const [activeAudio, setActiveAudio] = useState(null);

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
        setGlobalAnnotation({
            ...defaultAnnotationState, // SPREAD operator is now correctly used.
            vehicle_type: jumpToData.sourceEvent?.vehicle_type || '',
            location: jumpToData.sourceEvent?.location || defaultAnnotationState.location,
            action: jumpToData.sourceEvent?.action || defaultAnnotationState.action,
            direction: jumpToData.sourceEvent?.direction || defaultAnnotationState.direction,
            // I'm keeping the fix for the notes field as well for completeness.
            annotator_notes: (jumpToData.sourceEvent?.annotator_notes || jumpToData.sourceEvent?.annotation) || ''
        });
    }
  }, [jumpToData]);

  useEffect(() => {
    if (!selectedCollections.length || !startTime) {
        setChartData({}); setErrors({}); return;
    }
    const fetchAllWaveforms = async () => {
      setIsLoading(true); setChartData({}); setErrors({});
      const endTime = new Date(startTime.getTime() + durationSecs * 1000);
      const promises = selectedCollections.map(c =>
        axios.get('/api/audio/waveform', { params: { collection: c, start: startTime.toISOString(), end: endTime.toISOString(), points: 2000 } })
             .then(res => ({ collection: c, data: res.data, error: null }))
             .catch(err => ({ collection: c, data: [], error: err.response?.data?.detail || 'Failed' }))
      );
      const results = await Promise.all(promises);
      const newChartData = {}; const newErrors = {};
      results.forEach(result => {
        if (result.error) newErrors[result.collection] = result.error;
        else if (result.data?.length > 0) newChartData[result.collection] = result.data;
      });
      setChartData(newChartData); setErrors(newErrors); setIsLoading(false);
    };
    fetchAllWaveforms();
  }, [selectedCollections, startTime, durationSecs]);
  
  const handleChartClick = (timestamp, sensorId) => {
    const clickedDate = parseISOString(timestamp);
    if (selectionMode === 'fixed') {
        const halfWindowMs = (Number(fixedWindowSize) * 1000) / 2;
        setSelectionRange(prev => ({...prev, [sensorId]: { start: new Date(clickedDate.getTime() - halfWindowMs), end: new Date(clickedDate.getTime() + halfWindowMs) }}));
    } else {
        if (isSelecting !== sensorId) {
            setIsSelecting(sensorId);
            setSelectionRange(prev => ({ ...prev, [sensorId]: { start: clickedDate, end: null } }));
        } else {
            const [start, end] = [selectionRange[sensorId].start, clickedDate].sort((a, b) => a - b);
            setSelectionRange(prev => ({...prev, [sensorId]: { start, end }}));
            setIsSelecting('');
        }
    }
  };

  const handleGlobalFormChange = (field, value) => {
    setGlobalAnnotation(prev => ({ ...prev, [field]: value }));
  };

  const handleSaveAllAnnotations = async () => {
    const activeSelections = Object.entries(selectionRange).filter(([, range]) => range.start && range.end);
    if (activeSelections.length === 0) return alert("Please make a selection on at least one sensor chart.");
    if (!globalAnnotation.vehicle_type || !activeReviewEvent) return alert("Please select a vehicle type and ensure you are in a review session.");

    const promises = activeSelections.map(([sensorId, range]) => {
        const payload = {
            ...globalAnnotation,
            parent_event_id: activeReviewEvent.id,
            source_collection: sensorId,
            start_timestamp: range.start.toISOString(),
            end_timestamp: range.end.toISOString(),
        };
        console.log("PAYLOAD:", JSON.stringify(payload, null, 2));
        return axios.post('/api/annotations/refined', payload);
    });

    try {
        await Promise.all(promises);
        fetchRefinedAnnotations();
        setSelectionRange({});
    } catch (err) {
        alert(`Failed to save one or more annotations: ${err.response?.data?.detail || err.message}`);
    }
  };

  const handleCancelAll = () => {
    setSelectionRange({});
    setGlobalAnnotation(defaultAnnotationState);
  };
  
  const handleNavigate = (direction) => {
    if (!startTime) return;
    setStartTime(new Date(startTime.getTime() + (direction === 'next' ? 1 : -1) * durationSecs * 1000));
  };
  
  const handleListenToSelection = async (sensorId) => {
    const selection = selectionRange[sensorId];
    if (!selection || !selection.start || !selection.end) return;

    if (activeAudio) {
      activeAudio.pause();
    }

    try {
      const response = await axios.get('/api/audio/raw', {
        params: {
          collection: sensorId,
          start: selection.start.toISOString(),
          end: selection.end.toISOString(),
        },
        responseType: 'blob',
      });

      const audioUrl = URL.createObjectURL(response.data);
      const audio = new Audio(audioUrl);
      
      setActiveAudio(audio);
      audio.play();

      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        setActiveAudio(null);
      };

    } catch (error) {
      console.error(`Failed to fetch or play audio for ${sensorId}:`, error);
      alert(`Could not play audio clip. See console for details.`);
      setActiveAudio(null);
    }
  };

  const uniqueSortedSelectedCollections = useMemo(() => {
    return Array.from(new Set(selectedCollections)).sort((a, b) => sensorOrder.indexOf(a) - sensorOrder.indexOf(b));
  }, [selectedCollections, sensorOrder]);

  const numActiveSelections = Object.values(selectionRange).filter(r => r && r.start && r.end).length;

  return (
    <div className="workspace-container">
      <SensorSelector allCollections={collections} selectedCollections={selectedCollections} setSelectedCollections={setSelectedCollections} sensorOrder={sensorOrder} setSensorOrder={setSensorOrder} />
      
      <div className={`main-controls-panel ${activeReviewEvent ? 'review-mode' : ''}`}>
        <div className="controls-left">
            <div className="control-group">
                <span className="control-label">Window:</span>
                <div className="button-tabs">
                    {DURATION_OPTIONS.map(d => (
                        <button key={d} className={`tab-button ${d === durationSecs ? 'selected' : ''}`} onClick={() => setDurationSecs(d)}>{d}s</button>
                    ))}
                </div>
            </div>
            <div className="control-group">
                <span className="control-label">Selection:</span>
                <div className="button-tabs">
                    <button className={`tab-button ${selectionMode === 'manual' ? 'selected' : ''}`} onClick={() => setSelectionMode('manual')}>Manual</button>
                    <button className={`tab-button ${selectionMode === 'fixed' ? 'selected' : ''}`} onClick={() => setSelectionMode('fixed')}>Fixed</button>
                </div>
            </div>
            {selectionMode === 'fixed' && (
                <div className="control-group">
                    <div className="button-tabs">
                        {FIXED_WINDOW_OPTIONS.map(d => (
                            <button key={d} className={`tab-button ${d === fixedWindowSize ? 'selected' : ''}`} onClick={() => setFixedWindowSize(d)}>{d}s</button>
                        ))}
                    </div>
                </div>
            )}
        </div>
        
        <div className="controls-center">
            <div className="control-group">
                <button className="nav-button" onClick={() => handleNavigate('prev')}>{'<<'}</button>
                <input type="datetime-local" value={formatForInput(startTime)} onChange={(e) => setStartTime(new Date(e.target.value + 'Z'))} step="1"/>
                <button className="nav-button" onClick={() => handleNavigate('next')}>{'>>'}</button>
            </div>
        </div>

        {/* --- ADJUSTMENT --- 
          The review banner UI that was here has been removed to prevent duplication.
          The `ReviewSessionControls` component now handles this display.
        /* --- END ADJUSTMENT --- */}
      </div>

      <div className="multi-sensor-view-scrollable">
        {isLoading ? <div className="loading-message">Loading Chart Data...</div> : uniqueSortedSelectedCollections.map(sensorId => (
          <div key={sensorId} className="sensor-plot-container">
            <div className="sensor-header">
              <div className="sensor-title">
                <div className="sensor-color-dot" style={{ backgroundColor: generateSensorColor(sensorId) }}></div>
                <h3>{getSensorDisplayName(sensorId)}</h3>
              </div>
              <div className="sensor-header-controls">
                {errors[sensorId] && <div className="sensor-error">⚠️ {errors[sensorId]}</div>}
                <button 
                  className="listen-button"
                  onClick={() => handleListenToSelection(sensorId)}
                  disabled={!selectionRange[sensorId]?.end}
                  title={selectionRange[sensorId]?.end ? "Listen to selected range" : "Make a full selection to listen"}
                >
                  Listen
                </button>
              </div>
            </div>
            {(chartData[sensorId] && chartData[sensorId].length > 0) ? (
              <TimeSeriesChart 
                chartData={chartData[sensorId]} 
                onChartClick={(ts) => handleChartClick(ts, sensorId)} 
                selection={selectionRange[sensorId]} 
                color={generateSensorColor(sensorId)} 
              />
            ) : (
              <div className="no-data-message">{!errors[sensorId] && "No data available"}</div>
            )}
          </div>
        ))}
      </div>

      {isSelecting && <div className="selection-prompt">Click a second point on the <strong>{getSensorDisplayName(isSelecting)}</strong> chart to complete the selection... (or <button className="link-button" onClick={() => setIsSelecting('')}>Cancel</button>)</div>}

      <div className="global-annotation-container">
        <div className="global-form-header">
            <h3>Step 2: Describe the Event for All Selections</h3>
            <span className="selection-count-badge">{numActiveSelections} Selection{numActiveSelections !== 1 && 's'} Active</span>
        </div>
        <div className="form-grid">
            <select value={globalAnnotation.vehicle_type} onChange={(e) => handleGlobalFormChange('vehicle_type', e.target.value)}><option value="">-- Vehicle* --</option>{vehicleConfigs.map(v => <option key={v.id} value={v.id}>{v.displayName}</option>)}</select>
            <select value={globalAnnotation.location} onChange={(e) => handleGlobalFormChange('location', e.target.value)}><option value="tarmac">Tarmac</option><option value="fastpass">Fastpass</option><option value="jungle">Jungle</option></select>
            <select value={globalAnnotation.action} onChange={(e) => handleGlobalFormChange('action', e.target.value)}><option value="driveby">Driveby</option><option value="rev">Rev</option><option value="idle">Idle</option><option value="flying">Flying</option><option value="hover">Hover</option></select>
            <select value={globalAnnotation.direction} onChange={(e) => handleGlobalFormChange('direction', e.target.value)}><option value="towards_de">Towards DE</option><option value="towards_103">Towards 103</option><option value="na">N/A</option><option value="clockwise">clockwise</option><option value="counter-clockwise">counter-clockwise</option></select>
        </div>
        <textarea placeholder="Notes..." value={globalAnnotation.annotator_notes} onChange={(e) => handleGlobalFormChange('annotator_notes', e.target.value)} />
        <div className="form-actions">
            <button onClick={handleCancelAll} className="cancel-button">Clear Selections & Form</button>
            <button onClick={handleSaveAllAnnotations} className="save-button" disabled={numActiveSelections === 0}>Save {numActiveSelections} Annotation{numActiveSelections !== 1 && 's'}</button>
        </div>
      </div>

      <div className="event-log-container">
        <EventLog events={refinedAnnotations} onDeleteAnnotation={(id) => { if(window.confirm("Delete?")) { axios.delete(`/api/annotations/refined/${id}`).then(fetchRefinedAnnotations); }}} />
      </div>
    </div>
  );
}

export default AnnotationWorkspace;