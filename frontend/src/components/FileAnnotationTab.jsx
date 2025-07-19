// frontend/src/components/FileAnnotationTab.jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import IngestionView from './IngestionView';
import AnnotationWorkspace from './AnnotationWorkspace';
import ReviewSessionControls from './ReviewSessionControls'; // --- NEW: Import new component ---

function FileAnnotationTab({ jumpToData }) {
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState('');
  const [view, setView] = useState('ingestion');
  
  // --- NEW: State for the active review session ---
  const [activeReviewEvent, setActiveReviewEvent] = useState(null);

  const fetchCollections = async () => {
    try {
      const response = await axios.get('/api/audio/collections');
      setCollections(response.data);
      if (response.data.length > 0) {
        setView('workspace');
        if (!selectedCollection) {
          setSelectedCollection(response.data[0]);
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

  // --- MODIFIED: This now starts the review session ---
  useEffect(() => {
    if (jumpToData) {
      setView('workspace');
      setSelectedCollection(jumpToData.collection);
      setActiveReviewEvent(jumpToData.sourceEvent); // Start the session
    }
  }, [jumpToData]);

  const handleIngestionComplete = (newCollectionName) => {
    fetchCollections();
    setSelectedCollection(newCollectionName);
    setView('workspace');
  };

  // --- NEW: Handler to end the review session ---
  const handleEndReview = async () => {
    if (!activeReviewEvent) return;
    try {
      // Mark the original manual event as 'reviewed'
      await axios.put(`/api/events/${activeReviewEvent.id}/status`, { status: 'reviewed' });
      // Clear the session state
      setActiveReviewEvent(null);
    } catch (error) {
      alert(`Error: Could not mark event ${activeReviewEvent.id} as reviewed.`);
      console.error(error);
    }
  };

  return (
    <div style={{ width: '100%' }}>
      {/* --- NEW: Conditionally render the session controls --- */}
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
          // --- MODIFIED: Pass the active event, not a one-time source event ---
          activeReviewEvent={activeReviewEvent} 
        />
      )}
      <button onClick={() => setView(view === 'ingestion' ? 'workspace' : 'ingestion')} style={{marginTop: '20px'}}>
        {view === 'ingestion' ? 'Go to Workspace' : 'Go to Ingestion'}
      </button>
    </div>
  );
}

export default FileAnnotationTab;