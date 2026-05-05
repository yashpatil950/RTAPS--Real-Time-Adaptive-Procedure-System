import React, { useState, useEffect } from 'react';
import { clearUserAnalytics, getAllParticipants, clearAdminAnalytics, clearAnalytics } from '../data/analyticsStorage';
import { Users as UsersIcon, Trash2, UserX, AlertTriangle } from 'lucide-react';

const Users = () => {
  const [isAdmin, setIsAdmin] = useState(false);
  const [participants, setParticipants] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  // Get user data and load participants on component mount
  useEffect(() => {
    const userData = localStorage.getItem('currentParticipant');
    if (userData) {
      const user = JSON.parse(userData);
      setIsAdmin(user.role === 'admin');
    }
    
    // Load participants asynchronously
    const loadParticipants = async () => {
      try {
        setIsLoading(true);
        const participantsData = await getAllParticipants();
        setParticipants(participantsData);
      } catch (error) {
        console.error('Error loading participants:', error);
      } finally {
        setIsLoading(false);
      }
    };
    
    loadParticipants();
  }, []);

  const handleClearUserData = async (participantId, username) => {
    if (window.confirm(`Clear all data for ${username} (${participantId})?`)) {
      try {
        await clearUserAnalytics(participantId);
        const participantsData = await getAllParticipants();
        setParticipants(participantsData);
      } catch (error) {
        console.error('Error clearing user data:', error);
        alert('Failed to clear user data. Please try again.');
      }
    }
  };

  const handleClearAdminData = () => {
    if (window.confirm('Clear all admin test sessions?')) {
      clearAdminAnalytics();
      // Note: clearAdminAnalytics is not supported with API backend
      alert('Admin data clearing not supported with API backend');
    }
  };

  const handleClearAllData = () => {
    if (window.confirm('Clear ALL analytics data for ALL users? This action cannot be undone.')) {
      clearAnalytics();
      // Note: clearAnalytics is not supported with API backend
      alert('Data clearing not supported with API backend');
    }
  };

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h1>
          <p className="text-gray-600">You don't have permission to access this page.</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading users...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">User Management</h1>
        <p className="text-lg text-gray-600">
          Manage participants and their analytics data
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="tablet-card">
          <div className="flex items-center">
            <div className="p-3 bg-blue-100 rounded-lg">
              <UsersIcon className="w-6 h-6 text-blue-600" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600">Total Users</p>
              <p className="text-2xl font-bold text-gray-900">{participants.length}</p>
            </div>
          </div>
        </div>

        <div className="tablet-card">
          <div className="flex items-center">
            <div className="p-3 bg-green-100 rounded-lg">
              <UsersIcon className="w-6 h-6 text-green-600" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600">Active Users</p>
              <p className="text-2xl font-bold text-gray-900">
                {participants.filter(p => p.sessionCount > 0).length}
              </p>
            </div>
          </div>
        </div>

        <div className="tablet-card">
          <div className="flex items-center">
            <div className="p-3 bg-purple-100 rounded-lg">
              <UsersIcon className="w-6 h-6 text-purple-600" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600">Total Sessions</p>
              <p className="text-2xl font-bold text-gray-900">
                {participants.reduce((sum, p) => sum + p.sessionCount, 0)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Users List */}
      <div className="tablet-card">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-gray-900">All Participants</h2>
          <div className="text-sm text-gray-500">
            {participants.length} user{participants.length !== 1 ? 's' : ''} total
          </div>
        </div>

        {participants.length === 0 ? (
          <div className="text-center py-12">
            <UsersIcon className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No Users Found</h3>
            <p className="text-gray-600">No participants have completed any sessions yet.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {participants.map((participant) => (
              <div key={participant.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                <div className="flex items-center space-x-4">
                  <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                    <span className="text-lg font-bold text-blue-600">
                      {participant.id}
                    </span>
                  </div>
                  <div>
                    <div className="font-semibold text-gray-900 text-lg">{participant.username}</div>
                    <div className="text-sm text-gray-500">
                      {participant.sessionCount} session{participant.sessionCount !== 1 ? 's' : ''} • 
                      Last active: {new Date(participant.lastSession).toLocaleDateString()}
                    </div>
                  </div>
                </div>
                <div className="flex items-center space-x-3">
                  <div className="text-right">
                    <div className="text-sm font-medium text-gray-900">
                      {participant.sessionCount} sessions
                    </div>
                    <div className="text-xs text-gray-500">
                      ID: {participant.id}
                    </div>
                  </div>
                  <button
                    onClick={() => handleClearUserData(participant.id, participant.username)}
                    className="flex items-center space-x-2 px-3 py-2 bg-red-100 text-red-700 hover:bg-red-200 rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                    <span>Clear Data</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Admin Actions */}
      <div className="tablet-card">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Admin Actions</h2>
        <div className="flex flex-wrap gap-4">
          <button
            onClick={handleClearAdminData}
            className="flex items-center space-x-2 px-4 py-2 bg-yellow-100 text-yellow-700 hover:bg-yellow-200 rounded-lg transition-colors"
          >
            <UserX className="w-4 h-4" />
            <span>Clear Admin Test Data</span>
          </button>
          
          <button
            onClick={handleClearAllData}
            className="flex items-center space-x-2 px-4 py-2 bg-red-100 text-red-700 hover:bg-red-200 rounded-lg transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            <span>Clear All Data</span>
          </button>
        </div>
        <p className="text-sm text-gray-500 mt-3">
          ⚠️ These actions cannot be undone. Please be careful when clearing data.
        </p>
      </div>
    </div>
  );
};

export default Users;
