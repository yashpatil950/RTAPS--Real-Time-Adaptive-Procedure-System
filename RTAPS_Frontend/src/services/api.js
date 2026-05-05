// API service layer for RTAPS backend
const API_BASE_URL = 'https://1fvmmxvjr4.execute-api.us-east-1.amazonaws.com/prod/';

class ApiService {
  constructor() {
    this.baseURL = API_BASE_URL;
  }

  // Generic API call method
  async apiCall(endpoint, options = {}) {
    const normalizedEndpoint = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
    const url = `${this.baseURL}${normalizedEndpoint}`;
    const method = (options.method || 'GET').toUpperCase();
    const defaultHeaders = method === 'GET' || method === 'HEAD' || method === 'OPTIONS'
      ? {}
      : { 'Content-Type': 'application/json' };
    const config = {
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
      ...options,
    };

    try {
      const response = await fetch(url, config);
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.error || `HTTP error! status: ${response.status}`);
      }
      
      return data;
    } catch (error) {
      console.error('API call failed:', error);
      throw error;
    }
  }

  // User management methods
  async getUsers() {
    return this.apiCall('/users');
  }

  async getUser(userId) {
    return this.apiCall(`/users/${userId}`);
  }

  async createUser(userData) {
    return this.apiCall('/users', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
  }

  async updateUser(userId, userData) {
    return this.apiCall(`/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(userData),
    });
  }

  async deleteUser(userId) {
    return this.apiCall(`/users/${userId}`, {
      method: 'DELETE',
    });
  }

  // Session management methods
  async getSessions(userId = null) {
    const endpoint = userId ? `/sessions?userId=${userId}` : '/sessions';
    return this.apiCall(endpoint);
  }

  async getSession(sessionId) {
    return this.apiCall(`/sessions/${sessionId}`);
  }

  async createSession(sessionData) {
    return this.apiCall('/sessions', {
      method: 'POST',
      body: JSON.stringify(sessionData),
    });
  }

  async updateSession(sessionId, sessionData) {
    return this.apiCall(`/sessions/${sessionId}`, {
      method: 'PUT',
      body: JSON.stringify(sessionData),
    });
  }

  async deleteSession(sessionId) {
    return this.apiCall(`/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  }

  // Authentication helper methods
  async loginUser(username) {
    try {
      // First, try to find existing user (case-insensitive)
      const usersResponse = await this.getUsers();
      const existingUser = usersResponse.users.find(user => 
        user.username.toLowerCase() === username.toLowerCase()
      );

      if (existingUser) {
        // Return as-is to avoid requiring a PUT route
        return existingUser;
      }

      // If user doesn't exist, create new user
      const newUser = await this.createUser({
        username: username,
        role: 'user'
      });
      return newUser.user;
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  }

  // Analytics helper methods
  async getUserSessions(userId) {
    return this.getSessions(userId);
  }

  async saveSession(sessionData) {
    return this.createSession(sessionData);
  }

  // Get analytics summary for a user
  async getUserAnalytics(userId) {
    const sessionsResponse = await this.getUserSessions(userId);
    const sessions = sessionsResponse.sessions || [];

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

    return {
      total,
      byProcedure,
      avgTimeSec,
      sessions
    };
  }

  // Get all participants (for admin view)
  async getAllParticipants() {
    const usersResponse = await this.getUsers();
    const sessionsResponse = await this.getSessions();
    
    const users = usersResponse.users || [];
    const sessions = sessionsResponse.sessions || [];
    
    // Create participant summary - show ALL users, even those without sessions
    const participants = users.map(user => {
      const userSessions = sessions.filter(session => session.participantId === user.userId);
      const lastSession = userSessions.length > 0 
        ? userSessions.sort((a, b) => new Date(b.completedAt) - new Date(a.completedAt))[0]
        : null;

      return {
        id: user.userId,
        username: user.username,
        sessionCount: userSessions.length,
        lastSession: lastSession ? lastSession.completedAt : null,
        role: user.role,
        createdAt: user.createdAt,
        isActive: user.isActive
      };
    });

    // Sort by last session (users with sessions first), then by creation date
    return participants.sort((a, b) => {
      if (a.lastSession && b.lastSession) {
        return new Date(b.lastSession) - new Date(a.lastSession);
      } else if (a.lastSession && !b.lastSession) {
        return -1;
      } else if (!a.lastSession && b.lastSession) {
        return 1;
      } else {
        return new Date(b.createdAt) - new Date(a.createdAt);
      }
    });
  }
}

// Create and export a singleton instance
const apiService = new ApiService();
export default apiService;
