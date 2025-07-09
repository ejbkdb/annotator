// frontend/src/components/TimeSeriesChart.jsx

import React from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import annotationPlugin from 'chartjs-plugin-annotation';

// Register all the necessary components for Chart.js
ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler,
  annotationPlugin // Register the annotation plugin
);

const TimeSeriesChart = ({ chartData, onChartClick, selection }) => {
  if (!chartData || chartData.length === 0) {
    return <div style={{height: '320px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#888'}}>No waveform data to display for the selected range.</div>;
  }

  // Map our data into the format Chart.js expects
  const labels = chartData.map(d => new Date(d.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3, hour12: false }));
  const minData = chartData.map(d => d.min);
  const maxData = chartData.map(d => d.max);

  const data = {
    labels,
    datasets: [
      {
        label: 'Max Amplitude',
        data: maxData,
        borderColor: 'rgba(97, 218, 251, 0.8)',
        backgroundColor: 'rgba(97, 218, 251, 0.2)',
        pointRadius: 0,
        borderWidth: 1.5,
        tension: 0.1,
        fill: '+1', // Fill to the next dataset (index + 1)
      },
      {
        label: 'Min Amplitude',
        data: minData,
        borderColor: 'rgba(97, 218, 251, 0.8)',
        backgroundColor: 'rgba(40, 44, 52, 1)',
        pointRadius: 0,
        borderWidth: 1.5,
        tension: 0.1,
        fill: 'origin', // Fill down to the zero line
      },
    ],
  };

  // Convert selection timestamps to chart data indices for drawing the box
  let selectionIndices = null;
  if (selection && selection.start) {
    const startIndex = chartData.findIndex(d => new Date(d.time) >= new Date(selection.start));
    
    // If only the start is selected, highlight a single point
    let endIndex = startIndex;
    if (selection.end) {
      endIndex = chartData.findIndex(d => new Date(d.time) >= new Date(selection.end));
    }
    selectionIndices = {
        start: startIndex !== -1 ? startIndex : 0,
        end: endIndex !== -1 ? endIndex : chartData.length -1
    };
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    onClick: (event, elements) => {
        if (elements.length > 0) {
            const dataIndex = elements[0].index;
            const timestamp = chartData[dataIndex].time;
            onChartClick(timestamp); // Pass the click timestamp up to the parent
        }
    },
    plugins: {
      legend: { display: false },
      tooltip: { enabled: false },
      annotation: {
        annotations: {
          // If a selection exists, draw the annotation box
          ...(selectionIndices && {
            selectionBox: {
              type: 'box',
              xMin: selectionIndices.start,
              xMax: selectionIndices.end,
              backgroundColor: 'rgba(231, 111, 81, 0.25)',
              borderColor: 'rgba(231, 111, 81, 1)',
              borderWidth: 2,
            }
          })
        }
      }
    },
    scales: {
      x: {
        ticks: { color: '#999' },
        grid: { color: 'rgba(255, 255, 255, 0.1)' },
      },
      y: {
        ticks: { color: '#999' },
        grid: { color: 'rgba(255, 255, 255, 0.1)' },
      },
    },
  };

  return (
    <div style={{ height: '320px', padding: '10px' }}>
      <Line options={options} data={data} />
    </div>
  );
};

export default TimeSeriesChart;