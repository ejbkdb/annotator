// frontend/src/components/FileAnnotationTab.jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import IngestionView from './IngestionView';
import AnnotationWorkspace from './AnnotationWorkspace';
import ReviewSessionControls from './ReviewSessionControls';

// --- NEW: Define the preferred default collection here ---
const PREFERRED_DEFAULT_COLLECTION = 'l1_moth_no_foam';

function FileAnnotationTab({ jumpToData }) {
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState('');
  const [view, setView] = useState('ingestion');
  
  const [activeReviewEvent, setActiveReviewEvent] = useState(null);

  const fetchCollections = async () => {
    try {
      const response = await axios.get('/api/audio/collections');
      const fetchedCollections = response.data;
      setCollections(fetchedCollections);

      if (fetchedCollections.length > 0) {
        setView('workspace');
        // --- MODIFIED: Logic to set the selected collection ---
        if (!selectedCollection) {
          // Check if the preferred default exists in the fetched list
          if (fetchedCollections.includes(PREFERRED_DEFAULT_COLLECTION)) {
            setSelectedCollection(PREFERRED_DEFAULT_COLLECTION);
          } else {
            // Fallback to the first item if the preferred one isn't found
            setSelectedCollection(fetchedCollections[0]);
          }
        }
      } else {
        setView('ingestion');
      }
    } catch (error) {
      console.error("Failed to fetch collections:", error);
    }
  };

  useEffect(() => {
    fetchCollections();
  }, []);

  useEffect(() => {
    if (jumpToData) {
      setView('workspace');
      setSelectedCollection(jumpToData.collection);
      setActiveReviewEvent(jumpToData.sourceEvent);
    }
  }, [jumpToData]);

  const handleIngestionComplete = (newCollectionName) => {
    fetchCollections();
    setSelectedCollection(newCollectionName);
    setView('workspace');
  };

  const handleEndReview = async () => {
    if (!activeReviewEvent) return;
    try {
      // This logic should be reviewed. If all children are created, the parent is already 'reviewed'.
      // This button might be better as just "End Session" that clears the state.
      // For now, we'll leave the original PUT request but it might be redundant.
      await axios.put(`/api/events/${activeReviewEvent.id}/status`, { status: 'reviewed' });
      setActiveReviewEvent(null);
    } catch (error) {
      alert(`Error: Could not mark event ${activeReviewEvent.id} as reviewed.`);
      console.error(error);
    }
  };

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      {activeReviewEvent && (
        <ReviewSessionControls 
          sourceEvent={activeReviewEvent}
          onEndReview={handleEndReview}
        />
      )}
      
      {view === 'ingestion' && <IngestionView onIngestionComplete={handleIngestionComplete} />}
      {view === 'workspace' && (
        <AnnotationWorkspace
          collections={collections}
          selectedCollection={selectedCollection}
          setSelectedCollection={setSelectedCollection}
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