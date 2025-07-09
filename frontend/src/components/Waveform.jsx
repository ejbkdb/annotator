// frontend/src/components/Waveform.jsx (REPLACE with this code)
import React, { useEffect, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import axios from 'axios';

// --- NEW: Accept 'points' as a prop ---
const Waveform = ({ collection, start, end, points }) => {
  const waveformRef = useRef(null);
  const wavesurfer = useRef(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // ... (useEffect for creating wavesurfer is unchanged) ...
  useEffect(() => {
    if (!waveformRef.current) return;
    wavesurfer.current = WaveSurfer.create({
      container: waveformRef.current, waveColor: '#61dafb', progressColor: '#e76f51',
      cursorColor: 'white', barWidth: 3, barRadius: 2, height: 200,
    });
    return () => wavesurfer.current.destroy();
  }, []);


  // --- UPDATED: This effect now re-runs when 'points' changes ---
  useEffect(() => {
    // Also check for a valid 'points' prop
    if (!collection || !wavesurfer.current || !start || !end || !points) {
      wavesurfer.current?.empty();
      return;
    }

    const loadWaveformData = async () => {
      setLoading(true);
      setError('');
      try {
        // --- THE FIX: Use the 'points' prop in the API call ---
        const waveformRes = await axios.get(`/api/audio/waveform`, {
          params: { collection, start, end, points }
        });
        
        const rawPeaks = waveformRes.data;
        if (rawPeaks.length === 0) {
          setError(`No data found for the selected time range in "${collection}".`);
          wavesurfer.current.empty();
          return;
        }

        const absMax = rawPeaks.reduce((max, p) => Math.max(max, Math.abs(p.min), Math.abs(p.max)), 0);
        if (absMax === 0) {
            wavesurfer.current.empty();
            return;
        }

        const peaks = rawPeaks.flatMap(p => [p.min / absMax, p.max / absMax]);
        const duration = (new Date(end) - new Date(start)) / 1000;

        wavesurfer.current.load('', peaks, duration);

      } catch (err) {
        const errorMsg = err.response?.data?.detail || err.message;
        setError(`Failed to load data for "${collection}". ${errorMsg}`);
        wavesurfer.current.empty();
      } finally {
        setLoading(false);
      }
    };

    loadWaveformData();
  }, [collection, start, end, points]); // <-- Add 'points' to the dependency array

  return (
    <div>
      <div ref={waveformRef}></div>
      {loading && <p>Loading visualization for "{collection}"...</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
    </div>
  );
};

export default Waveform;