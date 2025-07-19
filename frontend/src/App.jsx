// frontend/src/App.jsx
import React, { useState } from 'react';
import { Tab, Tabs, TabList, TabPanel } from 'react-tabs';
import 'react-tabs/style/react-tabs.css';

import RealtimeAnnotationTab from './components/RealtimeAnnotationTab';
import FileAnnotationTab from './components/FileAnnotationTab';
import ReviewTab from './components/ReviewTab';

function App() {
  const [tabIndex, setTabIndex] = useState(0);
  const [jumpToData, setJumpToData] = useState(null);

  const handleJumpTo = (data) => {
    setJumpToData(data);
    setTabIndex(1); // Switch to the "File-based Annotation" tab
  };
  
  // --- MODIFIED: Clear jump data when user navigates away ---
  const handleTabSelect = (index) => {
    if (index !== 1) {
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
            <FileAnnotationTab jumpToData={jumpToData} />
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