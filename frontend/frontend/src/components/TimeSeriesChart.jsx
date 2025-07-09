// frontend/src/components/TimeSeriesChart.jsx (NEW FILE)
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
  Filler, // Import the Filler plugin
} from 'chart.js';

// Register all the necessary components for Chart.js
ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler
);

const TimeSeriesChart = ({ chartData }) => {
  if (!chartData || chartData.length === 0) {
    return <div style={{padding: '20px', color: '#aaa'}}>Select a time range to view data.</div>;
  }

  // Transform our data into the format Chart.js expects
  const labels = chartData.map(d => new Date(d.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }));
  const minData = chartData.map(d => d.min);
  const maxData = chartData.map(d => d.max);

  const data = {
    labels,
    datasets: [
      {
        label: 'Max Amplitude',
        data: maxData,
        borderColor: 'rgba(97, 218, 251, 0.8)', // Lighter, more visible blue
        backgroundColor: 'rgba(97, 218, 251, 0.2)', // Semi-transparent fill
        pointRadius: 0, // No dots on the line
        borderWidth: 1, // Thin line
        tension: 0.1,   // Slightly curve the line
        fill: '+1',     // Fill to the next dataset in the array (the 'min' dataset)
      },
      {
        label: 'Min Amplitude',
        data: minData,
        borderColor: 'rgba(97, 218, 251, 0.8)',
        backgroundColor: 'rgba(40, 44, 52, 1)', // Fill with the background color
        pointRadius: 0,
        borderWidth: 1,
        tension: 0.1,
        fill: 'origin', // Fill down to the zero line
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false, // Disable animation for faster rendering on navigation
    plugins: {
      legend: {
        display: false, // Hide the legend box
      },
      tooltip: {
        enabled: false, // Disable tooltips for a cleaner look
      },
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
    <div style={{ height: '300px', padding: '10px' }}>
      <Line options={options} data={data} />
    </div>
  );
};

export default TimeSeriesChart;