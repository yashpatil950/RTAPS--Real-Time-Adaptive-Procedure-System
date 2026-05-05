import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Play, Eye, Clock, CheckCircle, ChevronDown, ChevronUp, Train, Radio } from 'lucide-react';
import { getAllProcedures, getProceduresByTrain } from '../data/procedures';

const Dashboard = () => {
  const navigate = useNavigate();
  const [showSystemStatus, setShowSystemStatus] = useState(true);
  const [selectedTrain, setSelectedTrain] = useState(null); // null, 1, or 2
  const [procedures, setProcedures] = useState([]);

  // Load system status visibility preference from localStorage
  useEffect(() => {
    const savedPreference = localStorage.getItem('dashboard_showSystemStatus');
    if (savedPreference !== null) {
      setShowSystemStatus(JSON.parse(savedPreference));
    }
  }, []);

  // Update procedures when train is selected
  useEffect(() => {
    if (selectedTrain) {
      setProcedures(getProceduresByTrain(selectedTrain));
    } else {
      setProcedures([]);
    }
  }, [selectedTrain]);

  // Save system status visibility preference to localStorage
  const toggleSystemStatus = () => {
    const newValue = !showSystemStatus;
    setShowSystemStatus(newValue);
    localStorage.setItem('dashboard_showSystemStatus', JSON.stringify(newValue));
  };

  const handleStartSession = (procedureId) => {
    if (!selectedTrain) return;
    navigate(`/session/${procedureId}?train=${selectedTrain}`);
  };

  const handleViewProcedure = (procedureId) => {
    // For now, just show an alert - could be expanded to show procedure details
    alert(`Viewing procedure ${procedureId} details`);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Welcome to RTAPS: Real-Time Adaptive Procedure System</h1>
        {/* <p className="text-lg text-gray-600">
          Real-Time Adaptive Procedure System - Focus on step expansion based on time
        </p> */}
      </div>

      <div className="flex justify-center">
        <Link
          to="/streaming"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-medium shadow-md hover:bg-slate-800 transition-colors"
        >
          <Radio className="w-4 h-4 shrink-0" />
          Live eye-tracking &amp; ML dashboard
        </Link>
      </div>

      {/* System Status */}
      <div className="tablet-card">
        <div 
          className="flex items-center justify-between cursor-pointer hover:bg-gray-50 rounded-lg p-2 -m-2 transition-colors"
          onClick={toggleSystemStatus}
        >
          <div className="flex items-center space-x-3">
            <div className="w-3 h-3 bg-green-500 rounded-full"></div>
            <span className="text-sm font-medium text-gray-700">
              System Status - Ready for procedure execution
            </span>
          </div>
          <div className="flex items-center space-x-2">
            <div className="px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
              Online
            </div>
            {showSystemStatus ? (
              <ChevronUp className="w-4 h-4 text-gray-500" />
            ) : (
              <ChevronDown className="w-4 h-4 text-gray-500" />
            )}
          </div>
        </div>
        
        {showSystemStatus && (
          <div className="mt-4 pt-4 border-t border-gray-200">
            <p className="text-gray-600 text-sm">
              Ready for procedure execution with adaptive sub-step display
            </p>
          </div>
        )}
      </div>

      {/* Train Selection */}
      <div className="tablet-card">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Select Manufacturing Train</h2>
        <div className="grid grid-cols-2 gap-4 mb-6">
          <button
            onClick={() => setSelectedTrain(1)}
            className={`p-6 rounded-lg border-2 transition-all ${
              selectedTrain === 1
                ? 'border-blue-600 bg-blue-50 shadow-md'
                : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
            }`}
          >
            <div className="flex flex-col items-center">
              <Train className={`w-8 h-8 mb-2 ${selectedTrain === 1 ? 'text-blue-600' : 'text-gray-400'}`} />
              <h3 className="text-lg font-semibold text-gray-900 mb-1">Train 1</h3>
              <p className="text-sm text-gray-600">Select Train 1 procedures</p>
            </div>
          </button>
          
          <button
            onClick={() => setSelectedTrain(2)}
            className={`p-6 rounded-lg border-2 transition-all ${
              selectedTrain === 2
                ? 'border-blue-600 bg-blue-50 shadow-md'
                : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
            }`}
          >
            <div className="flex flex-col items-center">
              <Train className={`w-8 h-8 mb-2 ${selectedTrain === 2 ? 'text-blue-600' : 'text-gray-400'}`} />
              <h3 className="text-lg font-semibold text-gray-900 mb-1">Train 2</h3>
              <p className="text-sm text-gray-600">Select Train 2 procedures</p>
            </div>
          </button>
        </div>
      </div>

      {/* Available Procedures */}
      <div className="tablet-card">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">
          {selectedTrain ? `Available Procedures - Train ${selectedTrain}` : 'Available Procedures'}
        </h2>
        
        {!selectedTrain ? (
          <div className="text-center py-8">
            <Train className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">Please Select a Train</h3>
            <p className="text-gray-600">Select Train 1 or Train 2 above to view available procedures.</p>
          </div>
        ) : procedures.length === 0 ? (
          <div className="text-center py-8">
            <Clock className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No Procedures Available</h3>
            <p className="text-gray-600">Procedures will appear here once they are configured.</p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {procedures.map((procedure) => (
              <div key={procedure.id} className="bg-white rounded-lg border border-gray-200 p-6 hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-2">
                      {procedure.name}
                    </h3>
                    <p className="text-gray-600 text-sm">
                      {procedure.description}
                    </p>
                    <div className="text-xs text-gray-500 mt-2">
                      {procedure.steps.length} main steps
                    </div>
                  </div>
                </div>
                
                <div className="flex space-x-2">
                  <button
                    onClick={() => handleStartSession(procedure.id)}
                    className="flex-1 tablet-button bg-blue-600 text-white hover:bg-blue-700"
                  >
                    <Play className="w-4 h-4 mr-2" />
                    Start Session
                  </button>
                  
                  <button
                    onClick={() => handleViewProcedure(procedure.id)}
                    className="flex-1 tablet-button bg-gray-100 text-gray-700 hover:bg-gray-200"
                  >
                    <Eye className="w-4 h-4 mr-2" />
                    View Details
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="tablet-card text-center">
          <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mx-auto mb-3">
            <CheckCircle className="w-6 h-6 text-blue-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">{selectedTrain ? procedures.length : 0}</h3>
          <p className="text-gray-600">Available Procedures</p>
        </div>
        
        <div className="tablet-card text-center">
          <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mx-auto mb-3">
            <Play className="w-6 h-6 text-green-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">Ready</h3>
          <p className="text-gray-600">System Status</p>
        </div>
        
        <div className="tablet-card text-center">
          <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mx-auto mb-3">
            <Eye className="w-6 h-6 text-purple-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">Adaptive</h3>
          <p className="text-gray-600">Sub-step Display</p>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
