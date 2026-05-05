// API Service Layer for RTAPS Backend Integration
// This will replace localStorage calls with API calls

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://your-api-gateway-url.amazonaws.com/prod';

class APIService {
  constructor() {
    this.token = localStorage.getItem('authToken');
  }

  // Set authentication token
  setToken(token) {
    this.token = token;
    localStorage.setItem('authToken', token);
  }

  // Clear authentication token
  clearToken() {
    this.token = null;
    localStorage.removeItem('authToken');
  }

  // Generic API request method
  async request(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...(this.token && { Authorization: `Bearer ${this.token}` }),
        ...options.headers,
      },
      ...options,
    };

    try {
      const response = await fetch(url, config);
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'API request failed');
      }

      return await response.json();
    } catch (error) {
      console.error('API Error:', error);
      throw error;
    }
  }

  // Authentication APIs
  async register(userData) {
    return this.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
  }

  async login(username, password) {
    const response = await this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    
    if (response.token) {
      this.setToken(response.token);
    }
    
    return response;
  }

  async logout() {
    try {
      await this.request('/auth/logout', { method: 'POST' });
    } finally {
      this.clearToken();
    }
  }

  async getCurrentUser() {
    return this.request('/auth/me');
  }

  // User Management APIs
  async getUsers() {
    return this.request('/users');
  }

  async getUser(userId) {
    return this.request(`/users/${userId}`);
  }

  async updateUser(userId, userData) {
    return this.request(`/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(userData),
    });
  }

  async deleteUser(userId) {
    return this.request(`/users/${userId}`, {
      method: 'DELETE',
    });
  }

  // Session Management APIs
  async createSession(sessionData) {
    return this.request('/sessions', {
      method: 'POST',
      body: JSON.stringify(sessionData),
    });
  }

  async getSessions(userId = null) {
    const endpoint = userId ? `/sessions?userId=${userId}` : '/sessions';
    return this.request(endpoint);
  }

  async getSession(sessionId) {
    return this.request(`/sessions/${sessionId}`);
  }

  async updateSession(sessionId, sessionData) {
    return this.request(`/sessions/${sessionId}`, {
      method: 'PUT',
      body: JSON.stringify(sessionData),
    });
  }

  async deleteSession(sessionId) {
    return this.request(`/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  }

  // Analytics APIs
  async getAnalyticsSummary() {
    return this.request('/analytics/summary');
  }

  async getProcedureAnalytics() {
    return this.request('/analytics/by-procedure');
  }

  async getUserAnalytics(userId) {
    return this.request(`/analytics/user/${userId}`);
  }

  // Offline fallback methods (for backward compatibility)
  async getOfflineData() {
    // Fallback to localStorage if API is unavailable
    const participants = JSON.parse(localStorage.getItem('participants') || '[]');
    const analytics = JSON.parse(localStorage.getItem('rtaps_analytics_v1') || '{"sessions":[]}');
    
    return {
      participants,
      analytics: analytics.sessions || []
    };
  }

  // Check if API is available
  async isAPIAvailable() {
    try {
      await this.request('/health');
      return true;
    } catch {
      return false;
    }
  }
}

// Create singleton instance
const apiService = new APIService();

export default apiService;

// Migration helper functions
export const migrateFromLocalStorage = async () => {
  try {
    // Check if API is available
    const isOnline = await apiService.isAPIAvailable();
    if (!isOnline) {
      console.log('API not available, using offline mode');
      return false;
    }

    // Get existing localStorage data
    const participants = JSON.parse(localStorage.getItem('participants') || '[]');
    const analytics = JSON.parse(localStorage.getItem('rtaps_analytics_v1') || '{"sessions":[]}');

    // Migrate participants
    for (const participant of participants) {
      try {
        await apiService.register(participant);
      } catch (error) {
        console.warn('Failed to migrate participant:', participant.username, error);
      }
    }

    // Migrate sessions
    for (const session of analytics.sessions) {
      try {
        await apiService.createSession(session);
      } catch (error) {
        console.warn('Failed to migrate session:', session.sessionId, error);
      }
    }

    console.log('Migration completed successfully');
    return true;
  } catch (error) {
    console.error('Migration failed:', error);
    return false;
  }
};

// Hybrid mode: Try API first, fallback to localStorage
export const getData = async (type, ...args) => {
  try {
    const isOnline = await apiService.isAPIAvailable();
    if (isOnline) {
      // Use API
      switch (type) {
        case 'participants':
          return await apiService.getUsers();
        case 'sessions':
          return await apiService.getSessions(...args);
        case 'analytics':
          return await apiService.getAnalyticsSummary();
        default:
          throw new Error('Unknown data type');
      }
    } else {
      // Fallback to localStorage
      return await apiService.getOfflineData();
    }
  } catch (error) {
    console.warn('API failed, using offline data:', error);
    return await apiService.getOfflineData();
  }
};
