import React, { useState, useRef, useEffect } from 'react';
import './SensorSelector.css';

const generateSensorColor = (sensorName) => {
  const colors = [
    '#61dafb', '#2a9d8f', '#e76f51', '#f4a261', '#e9c46a', 
    '#264653', '#9b59b6', '#3498db', '#95a5a6', '#e67e22',
    '#1abc9c', '#f39c12', '#8e44ad', '#2980b9', '#34495e'
  ];
  let hash = 0;
  for (let i = 0; i < sensorName.length; i++) {
    const char = sensorName.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return colors[Math.abs(hash) % colors.length];
};

function SensorSelector({ 
  allCollections, 
  selectedCollections, 
  setSelectedCollections,
  sensorOrder,
  setSensorOrder
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [draggedItem, setDraggedItem] = useState(null);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    const newSensors = allCollections.filter(c => !sensorOrder.includes(c));
    if (newSensors.length > 0) {
      setSensorOrder(prev => [...prev, ...newSensors]);
    }
  }, [allCollections, sensorOrder, setSensorOrder]);

  const handleSensorToggle = (sensorId) => {
    setSelectedCollections(prev => {
      const newSelection = new Set(prev);
      if (newSelection.has(sensorId)) {
        newSelection.delete(sensorId);
      } else {
        newSelection.add(sensorId);
      }
      const orderedSelection = sensorOrder.filter(sensor => newSelection.has(sensor));
      return orderedSelection;
    });
  };
  
  const handleDrop = (e, targetSensorId) => {
    e.preventDefault();
    if (draggedItem && draggedItem !== targetSensorId) {
      const newOrder = [...sensorOrder];
      const draggedIndex = newOrder.indexOf(draggedItem);
      const targetIndex = newOrder.indexOf(targetSensorId);
      newOrder.splice(draggedIndex, 1);
      newOrder.splice(targetIndex, 0, draggedItem);
      setSensorOrder(newOrder);
      setSelectedCollections(currentSelected => newOrder.filter(sensor => currentSelected.includes(sensor)));
    }
    setDraggedItem(null);
  };

  const getSensorDisplayName = (sensorId) => sensorId.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

  const selectedCount = selectedCollections.length;
  const totalCount = allCollections.length;

  return (
    <div className="sensor-selector-container" ref={dropdownRef}>
      <div className="sensor-selector-header">
        <h3>Select Data Sensors</h3>
        <div className="sensor-selector-controls">
          {/* CORRECTED: Use functional update to guarantee state integrity */}
          <button onClick={() => setSelectedCollections(() => [])} className="control-button clear" disabled={selectedCount === 0}>Clear</button>
          {/* CORRECTED: Use a Set to merge and de-duplicate, preventing race conditions */}
          <button
            onClick={() =>
              setSelectedCollections(prev => {
                const next = new Set(prev);
                sensorOrder.forEach(s => { if (allCollections.includes(s)) next.add(s); });
                return Array.from(next);
              })
            }
            className="control-button all"
            disabled={selectedCount === totalCount}
          >
            All
          </button>
        </div>
      </div>
      <div className="dropdown-trigger" onClick={() => setIsOpen(!isOpen)}>
        <div className="selected-summary">
          {selectedCount === 0 ? <span className="placeholder-text">Choose sensors...</span> : (
            <div className="selected-sensors-preview">
              {selectedCollections.slice(0, 3).map(sensorId => (
                <div key={sensorId} className="sensor-chip">
                  <div className="sensor-color-dot" style={{ backgroundColor: generateSensorColor(sensorId) }} />
                  <span>{getSensorDisplayName(sensorId)}</span>
                </div>
              ))}
              {selectedCount > 3 && <span className="more-count">+{selectedCount - 3} more</span>}
            </div>
          )}
        </div>
        <div className="dropdown-arrow"><span className={`arrow ${isOpen ? 'open' : ''}`}>▼</span></div>
      </div>
      {isOpen && (
        <div className="dropdown-menu">
          <div className="dropdown-header">
            <span className="selection-count">{selectedCount} of {totalCount} selected</span>
            <span className="drag-hint">💡 Drag to reorder</span>
          </div>
          <div className="sensors-list">
            {sensorOrder.filter(s => allCollections.includes(s)).map((sensorId, index) => (
              <div
                key={sensorId}
                className={`sensor-item ${selectedCollections.includes(sensorId) ? 'selected' : ''} ${draggedItem === sensorId ? 'dragging' : ''}`}
                draggable
                onDragStart={(e) => setDraggedItem(sensorId)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => handleDrop(e, sensorId)}
                onDragEnd={() => setDraggedItem(null)}
              >
                <div className="drag-handle">⋮⋮</div>
                <label className="sensor-checkbox-label" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={selectedCollections.includes(sensorId)} onChange={() => handleSensorToggle(sensorId)} className="sensor-checkbox" />
                  <div className="sensor-info">
                    <div className="sensor-color-indicator" style={{ backgroundColor: generateSensorColor(sensorId) }} />
                    <div className="sensor-names">
                      <span className="sensor-display-name">{getSensorDisplayName(sensorId)}</span>
                      <span className="sensor-id">({sensorId})</span>
                    </div>
                  </div>
                </label>
                <div className="order-number">#{index + 1}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default SensorSelector;