// frontend/src/components/FileAnnotationTab.jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import IngestionView from './IngestionView';
import AnnotationWorkspace from './AnnotationWorkspace';

function FileAnnotationTab() {
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState('');
  const [view, setView] = useState('ingestion'); // 'ingestion' or 'workspace'

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

  const handleIngestionComplete = (newCollectionName) => {
    fetchCollections();
    setSelectedCollection(newCollectionName);
    setView('workspace');
  };

  return (
    <div style={{ width: '100%' }}>
      {view === 'ingestion' && <IngestionView onIngestionComplete={handleIngestionComplete} />}
      {view === 'workspace' && (
        <AnnotationWorkspace
          collections={collections}
          selectedCollection={selectedCollection}
          setSelectedCollection={setSelectedCollection}
        />
      )}
      <button onClick={() => setView(view === 'ingestion' ? 'workspace' : 'ingestion')} style={{marginTop: '20px'}}>
        {view === 'ingestion' ? 'Go to Workspace' : 'Go to Ingestion'}
      </button>
    </div>
  );
}

export default FileAnnotationTab;