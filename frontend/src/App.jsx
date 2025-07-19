// frontend/src/App.jsx
import React, { useState } from 'react';
import { Tab, Tabs, TabList, TabPanel } from 'react-tabs';
import 'react-tabs/style/react-tabs.css'; // Default styles

import RealtimeAnnotationTab from './components/RealtimeAnnotationTab';
import FileAnnotationTab from './components/FileAnnotationTab';
import ReviewTab from './components/ReviewTab';
import StatusBar from './components/StatusBar'; // Can be shared or moved

function App() {
  const [tabIndex, setTabIndex] = useState(0);
  const [jumpToData, setJumpToData] = useState(null);

  const handleJumpTo = (data) => {
    setJumpToData(data);
    setTabIndex(1); // Switch to the "File-based Annotation" tab
  };

  return (
    <div className="main-container">
      <header className="header"><h1>Test Range Annotation Tool</h1></header>
      <Tabs className="content-tabs" selectedIndex={tabIndex} onSelect={(index) => setTabIndex(index)}>
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
      {/* StatusBar can be enhanced to show context-specific info */}
    </div>
  );
}
export default App;