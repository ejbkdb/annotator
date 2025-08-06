// frontend/src/components/FileAnnotationTab.jsx
import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import IngestionView from './IngestionView';
import AnnotationWorkspace from './AnnotationWorkspace';
import ReviewSessionControls from './ReviewSessionControls';

function FileAnnotationTab({
  jumpToData,
  onJumpConsumed,
  selectedCollections,
  setSelectedCollections,
  sensorOrder,
  setSensorOrder
}) {
  const [collections, setCollections] = useState([]);
  const [view, setView] = useState('workspace');
  const [activeReviewEvent, setActiveReviewEvent] = useState(null);
  const [preReviewSelection, setPreReviewSelection] = useState(null);

  const fetchCollections = useCallback(async () => {
    try {
      const { data: fetchedCollections } = await axios.get('/api/audio/collections');
      setCollections(fetchedCollections);
      if (fetchedCollections.length > 0) {
        setView('workspace');
        setSensorOrder(prevOrder => {
          const combined = [...prevOrder, ...fetchedCollections];
          const unique = Array.from(new Set(combined));
          return unique.filter(sensor => fetchedCollections.includes(sensor));
        });
      } else {
        setView('ingestion');
      }
    } catch (error) {
      console.error("Failed to fetch collections:", error);
    }
  }, [setSensorOrder]);

  useEffect(() => {
    fetchCollections();
  }, [fetchCollections]);

  useEffect(() => {
    if (jumpToData) {
      if (selectedCollections.length > 0) {
        setPreReviewSelection({
          collections: selectedCollections,
          order: sensorOrder
        });
      }
      
      setSelectedCollections(jumpToData.collectionsToLoad);
      setActiveReviewEvent(jumpToData.sourceEvent);
      
      setSensorOrder(prev => {
        const combined = [...jumpToData.collectionsToLoad, ...prev];
        return Array.from(new Set(combined));
      });
      
      onJumpConsumed();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpToData, onJumpConsumed]);

  const handleEndReview = useCallback(async () => {
    if (preReviewSelection) {
      setSelectedCollections(preReviewSelection.collections);
      setSensorOrder(preReviewSelection.order);
    }
    try {
        await axios.put(`/api/events/${activeReviewEvent.id}/status`, { status: 'reviewed' });
    } catch(err) {
        alert("Could not update event status to 'reviewed'. Please check the console.")
        console.error("Failed to update event status:", err);
    }
    setPreReviewSelection(null);
    setActiveReviewEvent(null);
  }, [preReviewSelection, setSelectedCollections, setSensorOrder, activeReviewEvent]);

  const handleIngestionComplete = useCallback((newCollectionName) => {
    fetchCollections();
    if (!selectedCollections.includes(newCollectionName)) {
      setSelectedCollections(prev => [...prev, newCollectionName]);
    }
    setView('workspace');
  }, [selectedCollections, setSelectedCollections, fetchCollections]);

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      {view === 'ingestion' ? (
        <IngestionView onIngestionComplete={handleIngestionComplete} />
      ) : (
        <>
            <ReviewSessionControls sourceEvent={activeReviewEvent} onEndReview={handleEndReview} />
            <AnnotationWorkspace
                collections={collections}
                selectedCollections={selectedCollections}
                setSelectedCollections={setSelectedCollections}
                sensorOrder={sensorOrder}
                setSensorOrder={setSensorOrder}
                jumpToData={jumpToData}
                activeReviewEvent={activeReviewEvent}
                onEndReview={handleEndReview}
            />
        </>
      )}
      <button 
        onClick={() => setView(view === 'ingestion' ? 'workspace' : 'ingestion')} 
        style={{marginTop: 'auto', flexShrink: 0, padding: '10px'}}
      >
        {view === 'ingestion' ? 'Go to Workspace' : 'Go to Ingestion'}
      </button>
    </div>
  );
}

export default FileAnnotationTab;