import React, { useState } from 'react';
import { Tab, Tabs, TabList, TabPanel } from 'react-tabs';
import 'react-tabs/style/react-tabs.css';

import RealtimeAnnotationTab from './components/RealtimeAnnotationTab';
import FileAnnotationTab from './components/FileAnnotationTab';
import ReviewTab from './components/ReviewTab';

function App() {
  const [tabIndex, setTabIndex] = useState(0);
  const [jumpToData, setJumpToData] = useState(null);

  // State is lifted here to persist across tab navigation.
  const [selectedCollections, setSelectedCollections] = useState([]);
  const [sensorOrder, setSensorOrder] = useState([]);

  const handleJumpTo = (data) => {
    setJumpToData(data);
    setTabIndex(1); // Switch to the File-based Annotation tab
  };
  
  const handleTabSelect = (index) => {
    // Prevent stale review sessions if the user navigates away manually.
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
            {/* The persistent state is now passed down as props. */}
            <FileAnnotationTab 
              jumpToData={jumpToData}
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