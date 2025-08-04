// frontend/src/components/FileAnnotationTab.jsx
import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import IngestionView from './IngestionView';
import AnnotationWorkspace from './AnnotationWorkspace';

function FileAnnotationTab({
  jumpToData,
  // --- FIX: Receive the new handler prop ---
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

  // This effect fetches the list of all available collections once on mount.
  useEffect(() => {
    const fetchCollections = async () => {
      try {
        const { data: fetchedCollections } = await axios.get('/api/audio/collections');
        setCollections(fetchedCollections);
        if (fetchedCollections.length > 0) {
          setView('workspace');
          // Update the master sensor order with any new collections.
          setSensorOrder(prevOrder => {
            const combined = [...prevOrder, ...fetchedCollections];
            const unique = Array.from(new Set(combined));
            // Ensure any sensors that were removed from the backend are also removed.
            return unique.filter(sensor => fetchedCollections.includes(sensor));
          });
        } else {
          // If no collections exist, show the ingestion view.
          setView('ingestion');
        }
      } catch (error) {
        console.error("Failed to fetch collections:", error);
      }
    };
    fetchCollections();
  // The empty dependency array `[]` ensures this runs only once after the initial render.
  // We disable the exhaustive-deps lint rule here because setSensorOrder is stable
  // and we explicitly want this to run only once.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); 

  // --- FIX: This effect is now corrected to consume the jumpToData state only once ---
  useEffect(() => {
    // Only act if jumpToData has a value.
    if (jumpToData) {
      // 1. Save the current sensor selection to restore it later.
      // Note: We check if it's not an empty array to avoid saving a blank state
      // over a meaningful one if the user jumps immediately.
      if (selectedCollections.length > 0) {
        setPreReviewSelection(selectedCollections);
      }
      
      // 2. Set the selected collections for the review session.
      if (jumpToData.collectionsToLoad) {
        setSelectedCollections(jumpToData.collectionsToLoad);
      } else {
        // Fallback for older implementation.
        setSelectedCollections([jumpToData.collection]);
      }
      
      // 3. Set the active event to enter "review mode".
      setActiveReviewEvent(jumpToData.sourceEvent);
      
      // 4. Update the sensor order to prioritize the collections for this review.
      setSensorOrder(prev => {
        const newOrder = jumpToData.collectionsToLoad || [jumpToData.collection];
        const combined = [...newOrder, ...prev];
        return Array.from(new Set(combined));
      });
      
      // 5. CRITICAL FIX: Signal that the jump data has been consumed.
      onJumpConsumed();
    }
  // This effect now only depends on `jumpToData`. When it becomes null, the effect
  // does nothing. When it gets a value, it runs and then the value is cleared by the parent.
  // The other dependencies are stable setters or props that don't need to trigger this.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpToData]);

  // This function is passed down to end the review session.
  const handleEndReview = useCallback(() => {
    // Restore the previous sensor selection if one was saved.
    if (preReviewSelection !== null) {
      setSelectedCollections(preReviewSelection);
    }
    setPreReviewSelection(null);
    setActiveReviewEvent(null);
  }, [preReviewSelection, setSelectedCollections]);

  // This function handles the completion of a data ingestion task.
  const handleIngestionComplete = useCallback((newCollectionName) => {
    // Add the new collection to the master list.
    setCollections(prev => Array.from(new Set([...prev, newCollectionName])));
    // Automatically select the newly ingested collection.
    if (!selectedCollections.includes(newCollectionName)) {
      setSelectedCollections(prev => [...prev, newCollectionName]);
    }
    // Switch back to the main workspace view.
    setView('workspace');
  }, [selectedCollections, setSelectedCollections]);

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
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
          onEndReview={handleEndReview}
        />
      )}
      {/* The button to toggle between views remains at the bottom */}
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