import React, { useState, useEffect } from 'react';
import axios from 'axios';
import IngestionView from './IngestionView';
import AnnotationWorkspace from './AnnotationWorkspace';
import ReviewSessionControls from './ReviewSessionControls';

function FileAnnotationTab({ 
  jumpToData,
  selectedCollections,
  setSelectedCollections,
  sensorOrder,
  setSensorOrder
}) {
  const [collections, setCollections] = useState([]);
  const [view, setView] = useState('workspace');
  const [activeReviewEvent, setActiveReviewEvent] = useState(null);
  const [preReviewSelection, setPreReviewSelection] = useState(null);

  useEffect(() => {
    const fetchCollections = async () => {
      try {
        const { data: fetchedCollections } = await axios.get('/api/audio/collections');
        setCollections(fetchedCollections);

        if (fetchedCollections.length > 0) {
          setView('workspace');
          
          // CRITICAL FIX: Robustly merge and de-duplicate the sensor order.
          // This prevents duplicate entries from ever being added to the state.
          setSensorOrder(prevOrder => {
            const combined = [...prevOrder, ...fetchedCollections];
            const unique = Array.from(new Set(combined));
            // Ensure any sensors that were removed from the backend are also removed from the order.
            return unique.filter(sensor => fetchedCollections.includes(sensor));
          });

        } else {
          setView('ingestion');
        }
      } catch (error) {
        console.error("Failed to fetch collections:", error);
      }
    };
    fetchCollections();
  }, []); // This effect should only run once on component mount.

  useEffect(() => {
    if (jumpToData) {
      setPreReviewSelection(selectedCollections);
      setSelectedCollections([jumpToData.collection]);
      setActiveReviewEvent(jumpToData.sourceEvent);
      setSensorOrder(prev => [jumpToData.collection, ...prev.filter(s => s !== jumpToData.collection)]);
    }
  }, [jumpToData]);

  const handleEndReview = () => {
    if (preReviewSelection !== null) {
      setSelectedCollections(preReviewSelection);
    }
    setPreReviewSelection(null);
    setActiveReviewEvent(null);
  };

  const handleIngestionComplete = (newCollectionName) => {
    setCollections(prev => Array.from(new Set([...prev, newCollectionName])));
    if (!selectedCollections.includes(newCollectionName)) {
      setSelectedCollections(prev => [...prev, newCollectionName]);
    }
    setView('workspace');
  };

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      {activeReviewEvent && (
        <ReviewSessionControls 
          sourceEvent={activeReviewEvent}
          onEndReview={handleEndReview}
        />
      )}
      
      {view === 'ingestion' ? (
        <IngestionView onIngestionComplete={handleIngestionComplete} />
      ) : (
        <AnnotationWorkspace
          collections={collections}
          selectedCollections={selectedCollections}
          setSelectedCollections={setSelectedCollections}
          sensorOrder={sensorOrder}
          setSensorOrder={setSensorOrder}
          jumpToData={jumpToData}
          activeReviewEvent={activeReviewEvent}
        />
      )}
      <button onClick={() => setView(view === 'ingestion' ? 'workspace' : 'ingestion')} style={{marginTop: '20px', flexShrink: 0}}>
        {view === 'ingestion' ? 'Go to Workspace' : 'Go to Ingestion'}
      </button>
    </div>
  );
}

export default FileAnnotationTab;