// frontend/src/components/IngestionView.jsx
import React, { useState } from 'react';
import axios from 'axios';

function IngestionView({ onIngestionComplete }) {
  const [files, setFiles] = useState(null);
  const [collectionName, setCollectionName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');

  const handleFileChange = (e) => {
    setFiles(e.target.files);
  };

  const handleIngest = async () => {
    if (!files || files.length === 0 || !collectionName) {
      alert('Please select files and provide a collection name.');
      return;
    }
    setIsLoading(true);
    setStatusMessage('Uploading files...');

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }

    try {
      const uploadRes = await axios.post('/api/audio/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      setStatusMessage('Ingesting data into database...');
      const ingestFormData = new FormData();
      ingestFormData.append('collection_name', collectionName);
      uploadRes.data.filenames.forEach(name => ingestFormData.append('filenames', name));

      await axios.post('/api/audio/ingest', ingestFormData);

      setStatusMessage(`Successfully ingested files into '${collectionName}'.`);
      onIngestionComplete(collectionName);
    } catch (error) {
      const errorMsg = error.response?.data?.detail || error.message;
      setStatusMessage(`Error: ${errorMsg}`);
      console.error("Ingestion failed:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="ingestion-container">
      <h2>Ingest New Audio Data</h2>
      <div className="form-section">
        <label>1. Choose a Collection Name (New or Existing)</label>
        <input
          type="text"
          value={collectionName}
          onChange={(e) => setCollectionName(e.target.value.replace(/[^a-zA-Z0-9_-]/g, ''))}
          placeholder="e.g., 'highway_data_june_25'"
        />
      </div>
      <div className="form-section">
        <label>2. Select WAV Files</label>
        <input type="file" multiple accept=".wav" onChange={handleFileChange} />
      </div>
      <button onClick={handleIngest} disabled={isLoading} className="ingestion-button">
        {isLoading ? 'Processing...' : 'Start Ingestion'}
      </button>
      {statusMessage && <p>{statusMessage}</p>}
    </div>
  );
}
export default IngestionView;