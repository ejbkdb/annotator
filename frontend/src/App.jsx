// frontend/src/App.jsx
import React, { useState, useEffect } from 'react';
import { Tab, Tabs, TabList, TabPanel } from 'react-tabs';
import 'react-tabs/style/react-tabs.css';

import RealtimeAnnotationTab from './components/RealtimeAnnotationTab';
import FileAnnotationTab from './components/FileAnnotationTab';
import ReviewTab from './components/ReviewTab';

// Custom hook to manage state that persists in localStorage
const usePersistentState = (key, defaultValue) => {
  const [state, setState] = useState(() => {
    try {
      const storedValue = localStorage.getItem(key);
      return storedValue ? JSON.parse(storedValue) : defaultValue;
    } catch (error) {
      console.error(`Error reading '${key}' from localStorage`, error);
      return defaultValue;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(state));
    } catch (error) {
      console.error(`Error writing '${key}' to localStorage`, error);
    }
  }, [key, state]);

  return [state, setState];
};

function App() {
  const [tabIndex, setTabIndex] = useState(0);
  const [jumpToData, setJumpToData] = useState(null);

  // State is lifted and made persistent here.
  const [selectedCollections, setSelectedCollections] = usePersistentState('selectedCollections', []);
  const [sensorOrder, setSensorOrder] = usePersistentState('sensorOrder', []);

  const handleJumpTo = (data) => {
    setJumpToData(data);
    setTabIndex(1); // Switch to the File-based Annotation tab
  };
  
  const handleJumpConsumed = () => {
    setJumpToData(null);
  };

  const handleTabSelect = (index) => {
    if (index !== 1 && jumpToData) {
      setJumpToData(null);
    }
    setTabIndex(index);
  }

  return (
    <div className="main-container">
      <Tabs className="content-tabs" selectedIndex={tabIndex} onSelect={handleTabSelect}>
        <TabList>
          <Tab>Real-time Annotation</Tab>
          <Tab>File-based Annotation</Tab>
          <Tab>Review Manual Events</Tab>
        </TabList>

        <TabPanel>
          <div className="content-container">
            <RealtimeAnnotationTab />
          </div>
        </TabPanel>
        <TabPanel>
          <div className="content-container file-based-container">
            <FileAnnotationTab 
              jumpToData={jumpToData}
              onJumpConsumed={handleJumpConsumed}
              selectedCollections={selectedCollections}
              setSelectedCollections={setSelectedCollections}
              sensorOrder={sensorOrder}
              setSensorOrder={setSensorOrder}
            />
          </div>
        </TabPanel>
        <TabPanel>
            <div className="content-container file-based-container">
                <ReviewTab onJumpTo={handleJumpTo} />
            </div>
        </TabPanel>
      </Tabs>
    </div>
  );
}
export default App;