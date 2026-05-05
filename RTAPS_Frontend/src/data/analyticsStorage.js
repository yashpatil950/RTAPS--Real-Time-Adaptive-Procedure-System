// Analytics storage using API backend
// This replaces localStorage with API calls

import apiService from '../services/api';

// Get current user from localStorage
function getCurrentUser() {
  try {
    const userData = localStorage.getItem('currentParticipant');
    return userData ? JSON.parse(userData) : null;
  } catch (error) {
    console.error('Error getting current user:', error);
    return null;
  }
}

// Load all analytics records from API
export async function loadAnalytics() {
  try {
    const currentUser = getCurrentUser();
    if (!currentUser || currentUser.role === 'admin') {
      // For admin, get all sessions
      const response = await apiService.getSessions();
      return { sessions: response.sessions || [] };
    } else {
      // For regular users, get their sessions
      const response = await apiService.getUserSessions(currentUser.id);
      return { sessions: response.sessions || [] };
    }
  } catch (error) {
    console.error('Error loading analytics:', error);
    return { sessions: [] };
  }
}

// Append a completed session summary to API
export async function appendCompletedSession(sessionSummary) {
  try {
    const currentUser = getCurrentUser();
    if (!currentUser) {
      console.error('No current user found');
      return;
    }

    const sessionData = {
      participantId: currentUser.id,
      participantUsername: currentUser.username,
      procedureId: sessionSummary.procedureId,
      procedureName: sessionSummary.procedureName || null,
      totalTimeSec: sessionSummary.totalTimeSec,
      steps: sessionSummary.steps || [],
      trainNumber: sessionSummary.trainNumber || null,
      metadata: {
        ...sessionSummary.metadata,
        completedAt: new Date().toISOString()
      }
    };

    await apiService.saveSession(sessionData);
  } catch (error) {
    console.error('Error saving session:', error);
    throw error;
  }
}

// Get analytics summary from API
export async function getSummary() {
  try {
    const currentUser = getCurrentUser();
    if (!currentUser) {
      return { total: 0, byProcedure: {}, avgTimeSec: 0 };
    }

    if (currentUser.role === 'admin') {
      // For admin, get summary of all sessions
      const response = await apiService.getSessions();
      const sessions = response.sessions || [];
      
      const total = sessions.length;
      const byProcedure = {};
      let totalTime = 0;
      
      sessions.forEach(session => {
        totalTime += session.totalTimeSec || 0;
        const key = session.procedureId;
        byProcedure[key] = byProcedure[key] || { count: 0, totalTimeSec: 0 };
        byProcedure[key].count += 1;
        byProcedure[key].totalTimeSec += session.totalTimeSec || 0;
      });
      
      const avgTimeSec = total ? Math.round(totalTime / total) : 0;
      return { total, byProcedure, avgTimeSec };
    } else {
      // For regular users, get their analytics
      return await apiService.getUserAnalytics(currentUser.id);
    }
  } catch (error) {
    console.error('Error getting summary:', error);
    return { total: 0, byProcedure: {}, avgTimeSec: 0 };
  }
}

// Clear analytics (not applicable for API - sessions are permanent)
export function clearAnalytics() {
  console.warn('clearAnalytics not supported with API backend');
}

// Clear analytics for a specific user (admin only)
export async function clearUserAnalytics(participantId) {
  try {
    const currentUser = getCurrentUser();
    if (currentUser?.role !== 'admin') {
      console.warn('Only admin can clear user analytics');
      return;
    }

    // Get user's sessions and delete them
    const response = await apiService.getUserSessions(participantId);
    const sessions = response.sessions || [];
    
    for (const session of sessions) {
      await apiService.deleteSession(session.sessionId);
    }
  } catch (error) {
    console.error('Error clearing user analytics:', error);
    throw error;
  }
}

// Get all unique participants from API
export async function getAllParticipants() {
  try {
    return await apiService.getAllParticipants();
  } catch (error) {
    console.error('Error getting participants:', error);
    return [];
  }
}

// Clear only admin test data (not applicable for API)
export function clearAdminAnalytics() {
  console.warn('clearAdminAnalytics not supported with API backend');
}