// frontend/src/components/PipelineManager.jsx
import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import './PipelineManager.css';

// Mock API, replace with actual calls
const MOCK_PIPELINES = [
    { id: 'prod_pipeline_v1', description: 'Main production pipeline for moth classification' },
    { id: 'test_alignment_pipe', description: 'Pipeline for testing new alignment offsets' }
];

const MOCK_HISTORY = {
    'prod_pipeline_v1': [
        { sensor_id: 'l1_moth_foam', last_processed_utc: '2024-07-30T10:00:00Z', last_run_utc: '2024-07-30T10:05:00Z' },
        { sensor_id: 'l2_moth_foam', last_processed_utc: '2024-07-30T09:45:00Z', last_run_utc: '2024-07-30T10:05:00Z' },
    ],
};

function PipelineManager() {
    const [pipelines, setPipelines] = useState(MOCK_PIPELINES);
    const [selectedPipelineId, setSelectedPipelineId] = useState(null);
    const [config, setConfig] = useState(null);
    const [history, setHistory] = useState(null);
    const [status, setStatus] = useState({});
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    
    const fetchPipelineStatus = useCallback(async (pipelineId) => {
        if (!pipelineId) return;
        try {
            const response = await axios.get(`/api/pipeline/${pipelineId}/status`);
            setStatus(prev => ({ ...prev, [pipelineId]: response.data }));
        } catch (err) {
            setStatus(prev => ({ ...prev, [pipelineId]: { error: 'Failed to fetch status' } }));
        }
    }, []);
    
    useEffect(() => {
        // Fetch list of pipelines on mount
        // In a real app, this would be an API call
        if (MOCK_PIPELINES.length > 0) {
            setSelectedPipelineId(MOCK_PIPELINES[0].id);
        }
    }, []);

    useEffect(() => {
        if (selectedPipelineId) {
            // Mock fetching config and history
            // setConfig(...)
            setHistory(MOCK_HISTORY[selectedPipelineId] || []);
            const interval = setInterval(() => fetchPipelineStatus(selectedPipelineId), 5000);
            fetchPipelineStatus(selectedPipelineId); // Initial fetch
            return () => clearInterval(interval);
        }
    }, [selectedPipelineId, fetchPipelineStatus]);

    const handleRunPipeline = async () => {
        if (!selectedPipelineId) return;
        setLoading(true);
        setError('');
        try {
            await axios.post(`/api/pipeline/${selectedPipelineId}/run`);
            alert('Pipeline run initiated!');
            setTimeout(() => fetchPipelineStatus(selectedPipelineId), 2000); // Fetch status after a short delay
        } catch (err) {
            setError(`Failed to run pipeline: ${err.response?.data?.detail || err.message}`);
        } finally {
            setLoading(false);
        }
    };
    
    const handleSaveConfig = () => {
        // Placeholder for saving config changes
        alert('Saving configuration is not yet implemented.');
    };

    const handleOffsetChange = (sensorId, value) => {
        // Placeholder for updating config state
        console.log(`Offset for ${sensorId} changed to ${value}`);
    };

    return (
        <div className="pipeline-manager">
            <h1>Pipeline Manager</h1>
            <div className="pipeline-selector">
                <label htmlFor="pipeline-select">Select Pipeline:</label>
                <select 
                    id="pipeline-select"
                    value={selectedPipelineId || ''}
                    onChange={e => setSelectedPipelineId(e.target.value)}
                >
                    {pipelines.map(p => <option key={p.id} value={p.id}>{p.id}</option>)}
                </select>
                <button onClick={handleRunPipeline} disabled={!selectedPipelineId || loading}>
                    {loading ? 'Running...' : 'Run Incremental Process'}
                </button>
            </div>
            {error && <div className="error-message">{error}</div>}

            <div className="pipeline-details">
                <div className="panel config-panel">
                    <h2>Configuration</h2>
                    <p>Configuration UI is not yet implemented. Use the API or CLI to create/update configs.</p>
                    <button onClick={handleSaveConfig} disabled>Save Changes</button>
                </div>

                <div className="panel history-panel">
                    <h2>Processing History</h2>
                    <table>
                        <thead>
                            <tr><th>Sensor</th><th>Last Processed (UTC)</th><th>Last Run (UTC)</th></tr>
                        </thead>
                        <tbody>
                            {history && history.length > 0 ? history.map(h => (
                                <tr key={h.sensor_id}>
                                    <td>{h.sensor_id}</td>
                                    <td>{new Date(h.last_processed_utc).toLocaleString()}</td>
                                    <td>{new Date(h.last_run_utc).toLocaleString()}</td>
                                </tr>
                            )) : <tr><td colSpan="3">No history available.</td></tr>}
                        </tbody>
                    </table>
                </div>
                
                <div className="panel offsets-panel">
                    <h2>Time Offsets (ms)</h2>
                     <div className="offset-item">
                        <span>l2_moth_foam</span>
                        <input type="number" defaultValue={-523} onChange={(e) => handleOffsetChange('l2_moth_foam', e.target.value)} />
                    </div>
                     <div className="offset-item">
                        <span>l3_moth_foam</span>
                        <input type="number" defaultValue={1247} onChange={(e) => handleOffsetChange('l3_moth_foam', e.target.value)} />
                    </div>
                    <button onClick={() => alert('Offset adjustment not implemented.')}>Apply Offsets</button>
                </div>
            </div>
        </div>
    );
}

export default PipelineManager;