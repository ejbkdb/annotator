// frontend/src/App.jsx
import React from 'react';
import { Tab, Tabs, TabList, TabPanel } from 'react-tabs';
import 'react-tabs/style/react-tabs.css'; // Default styles

import RealtimeAnnotationTab from './components/RealtimeAnnotationTab';
import FileAnnotationTab from './components/FileAnnotationTab';
import StatusBar from './components/StatusBar'; // Can be shared or moved

function App() {
  return (
    <div className="main-container">
      <header className="header"><h1>Test Range Annotation Tool</h1></header>
      <Tabs className="content-tabs">
        <TabList>
          <Tab>Real-time Annotation</Tab>
          <Tab>File-based Annotation</Tab>
        </TabList>

        <TabPanel>
          <div className="content-container">
            <RealtimeAnnotationTab />
          </div>
        </TabPanel>
        <TabPanel>
          <div className="content-container file-based-container">
            <FileAnnotationTab />
          </div>
        </TabPanel>
      </Tabs>
      {/* StatusBar can be enhanced to show context-specific info */}
    </div>
  );
}
export default App;