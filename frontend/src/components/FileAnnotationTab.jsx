// frontend/src/components/FileAnnotationTab.jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import IngestionView from './IngestionView';
import AnnotationWorkspace from './AnnotationWorkspace';
import ReviewSessionControls from './ReviewSessionControls';

function FileAnnotationTab({ jumpToData }) {
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState('');
  const [view, setView] = useState('ingestion');
  
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
      await axios.put(`/api/events/${activeReviewEvent.id}/status`, { status: 'reviewed' });
      setActiveReviewEvent(null);
    } catch (error) {
      alert(`Error: Could not mark event ${activeReviewEvent.id} as reviewed.`);
      console.error(error);
    }
  };

  return (
    // --- MODIFIED: Added height: 100% to allow child to fill the space ---
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