import React from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler,
} from 'chart.js';
import annotationPlugin from 'chartjs-plugin-annotation';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler,
  annotationPlugin
);

const hexToRgba = (hex, alpha) => {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

const TimeSeriesChart = ({ chartData, onChartClick, onChartHover, selection, color = '#61dafb' }) => {
  if (!chartData || chartData.length === 0) {
    return null;
  }

  const data = {
    labels: chartData.map(d => new Date(d.time).toISOString()),
    datasets: [
      {
        data: chartData.map(d => d.max),
        borderColor: color,
        backgroundColor: hexToRgba(color, 0.2),
        pointRadius: 0, borderWidth: 1.5, tension: 0.1, fill: '+1',
      },
      {
        data: chartData.map(d => d.min),
        borderColor: color,
        backgroundColor: hexToRgba('#282c34', 1),
        pointRadius: 0, borderWidth: 1.5, tension: 0.1, fill: 'origin',
      },
    ],
  };

  let selectionIndices = null;
  if (selection?.start) {
    const startIndex = chartData.findIndex(d => new Date(d.time) >= selection.start);
    let endIndex = startIndex;
    if (selection.end) {
      endIndex = chartData.findIndex(d => new Date(d.time) >= selection.end);
    }
    selectionIndices = {
        start: startIndex !== -1 ? startIndex : 0,
        end: endIndex !== -1 ? endIndex : chartData.length -1
    };
  }

  const options = {
    responsive: true, maintainAspectRatio: false, animation: false,
    onHover: (event, elements) => {
        if (onChartHover && elements.length > 0) {
            onChartHover(chartData[elements[0].index].time);
        }
    },
    onClick: (event, elements) => {
        if (elements.length > 0 && chartData[elements[0].index]) {
            onChartClick(chartData[elements[0].index].time);
        }
    },
    plugins: {
      legend: { display: false }, tooltip: { enabled: false },
      annotation: {
        annotations: {
          ...(selectionIndices && {
            selectionBox: {
              type: 'box', xMin: selectionIndices.start, xMax: selectionIndices.end,
              backgroundColor: 'rgba(231, 111, 81, 0.25)',
              borderColor: 'rgba(231, 111, 81, 1)', borderWidth: 2,
            }
          })
        }
      }
    },
    scales: {
      x: { ticks: { color: '#999', maxRotation: 0, autoSkip: true, maxTicksLimit: 10 }, grid: { color: 'rgba(255, 255, 255, 0.1)' } },
      y: { ticks: { color: '#999' }, grid: { color: 'rgba(255, 255, 255, 0.1)' } },
    },
  };

  return (
    <div style={{ height: '320px', padding: '10px' }}>
      <Line options={options} data={data} />
    </div>
  );
};

export default TimeSeriesChart;