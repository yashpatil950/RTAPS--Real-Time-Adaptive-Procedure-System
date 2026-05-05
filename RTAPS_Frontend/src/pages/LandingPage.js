import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import apiService from '../services/api';

const LandingPage = () => {
  const [showUserForm, setShowUserForm] = useState(false);
  const [userType, setUserType] = useState(''); // 'new' or 'returning'
  const [username, setUsername] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [usernameError, setUsernameError] = useState('');
  const [isCheckingAvailability, setIsCheckingAvailability] = useState(false);
  const [availabilityStatus, setAvailabilityStatus] = useState(''); // 'available', 'taken', 'checking', 'found'
  const navigate = useNavigate();

  // Check if username is available (for new users)
  const isUsernameAvailable = async (username) => {
    try {
      console.log('Checking username availability for:', username);
      const response = await apiService.getUsers();
      console.log('API response:', response);
      const users = response.users || [];
      const isAvailable = !users.some(p => p.username.toLowerCase() === username.toLowerCase());
      console.log('Username available:', isAvailable);
      return isAvailable;
    } catch (error) {
      console.error('Error checking username availability:', error);
      return false;
    }
  };

  // Check if username exists (for returning users)
  const isUsernameFound = async (username) => {
    try {
      console.log('Checking username existence for:', username);
      const response = await apiService.getUsers();
      console.log('API response:', response);
      const users = response.users || [];
      const foundUser = users.find(p => p.username.toLowerCase() === username.toLowerCase());
      console.log('Username found:', foundUser);
      return foundUser;
    } catch (error) {
      console.error('Error checking username existence:', error);
      return null;
    }
  };

  // Validate username format
  const validateUsernameFormat = (username) => {
    const usernamePattern = /^[a-zA-Z0-9_-]+$/; // Only letters, numbers, hyphens, underscores
    return usernamePattern.test(username) && username.length >= 3 && username.length <= 20;
  };

  // Check availability/existence with debouncing
  useEffect(() => {
    if (!username || username.length < 3) {
      setAvailabilityStatus('');
      setUsernameError('');
      return;
    }

    if (!validateUsernameFormat(username)) {
      setAvailabilityStatus('');
      setUsernameError('Username must be 3-20 characters, letters, numbers, hyphens, and underscores only');
      return;
    }

    setIsCheckingAvailability(true);
    setUsernameError('');

    const timeoutId = setTimeout(async () => {
      try {
        if (userType === 'new') {
          const isAvailable = await isUsernameAvailable(username);
          setAvailabilityStatus(isAvailable ? 'available' : 'taken');
        } else if (userType === 'returning') {
          const foundUser = await isUsernameFound(username);
          setAvailabilityStatus(foundUser ? 'found' : 'not-found');
        }
      } catch (error) {
        console.error('Error checking username:', error);
        setAvailabilityStatus('');
        setUsernameError('Error checking username. Please try again.');
      }
      setIsCheckingAvailability(false);
    }, 500); // 500ms debounce

    return () => clearTimeout(timeoutId);
  }, [username, userType]);

  const handleUserSubmit = async (e) => {
    e.preventDefault();
    
    // Clear previous errors
    setUsernameError('');

    // Validate username
    if (!username.trim()) {
      setUsernameError('Please enter a username');
      return;
    }

    if (!validateUsernameFormat(username)) {
      setUsernameError('Username must be 3-20 characters, letters, numbers, hyphens, and underscores only');
      return;
    }

    // Validate based on user type
    if (userType === 'new' && availabilityStatus !== 'available') {
      setUsernameError('Please choose an available username');
      return;
    }

    if (userType === 'returning' && availabilityStatus !== 'found') {
      setUsernameError('Username not found. Please check your username or create a new account.');
      return;
    }

    setIsLoading(true);
    
    try {
      // Use API service for both new and returning users
      const user = await apiService.loginUser(username.trim());
      
      // Store user data in localStorage for compatibility with existing app
      const participantData = {
        id: user.userId,
        username: user.username,
        role: user.role,
        createdAt: user.createdAt
      };
      
      localStorage.setItem('currentParticipant', JSON.stringify(participantData));
      
      // The App component will automatically detect the localStorage change and redirect
    } catch (error) {
      console.error('Login error:', error);
      setUsernameError('Login failed. Please try again.');
      setIsLoading(false);
    }
  };

  const handleAdminAccess = () => {
    const adminData = {
      role: 'admin',
      accessedAt: new Date().toISOString()
    };
    localStorage.setItem('currentParticipant', JSON.stringify(adminData));
    // The App component will automatically detect the localStorage change and redirect
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 relative overflow-hidden">
      {/* Animated Spider Web Background */}
      <div className="absolute inset-0 opacity-20">
        <svg className="w-full h-full" viewBox="0 0 1000 1000">
          {/* Web Structure */}
          <defs>
            <radialGradient id="webGradient" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.8"/>
              <stop offset="100%" stopColor="#1e1b4b" stopOpacity="0.3"/>
            </radialGradient>
          </defs>
          
          {/* Central Hub */}
          <circle cx="500" cy="500" r="8" fill="#8b5cf6" className="animate-pulse"/>
          
          {/* Radial Lines */}
          {Array.from({ length: 12 }, (_, i) => {
            const angle = (i * 30) * Math.PI / 180;
            const x2 = 500 + 400 * Math.cos(angle);
            const y2 = 500 + 400 * Math.sin(angle);
            return (
              <line
                key={i}
                x1="500"
                y1="500"
                x2={x2}
                y2={y2}
                stroke="#8b5cf6"
                strokeWidth="1"
                opacity="0.6"
                className="animate-pulse"
                style={{ animationDelay: `${i * 0.1}s` }}
              />
            );
          })}
          
          {/* Concentric Circles */}
          {[150, 250, 350].map((radius, i) => (
            <circle
              key={i}
              cx="500"
              cy="500"
              r={radius}
              fill="none"
              stroke="#8b5cf6"
              strokeWidth="1"
              opacity="0.4"
              strokeDasharray="5,5"
              className="animate-spin"
              style={{ 
                animationDuration: `${20 + i * 10}s`,
                animationDirection: i % 2 === 0 ? 'normal' : 'reverse'
              }}
            />
          ))}
          
          {/* Floating Particles */}
          {Array.from({ length: 20 }, (_, i) => (
            <circle
              key={i}
              cx={200 + (i * 40) % 600}
              cy={200 + (i * 60) % 600}
              r="2"
              fill="#8b5cf6"
              opacity="0.6"
              className="animate-pulse"
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          ))}
        </svg>
      </div>

      {/* Main Content */}
      <div className="relative z-10 flex items-center justify-center min-h-screen px-4">
        <div className="max-w-md w-full">
          {/* Logo/Title */}
          <div className="text-center mb-12">
            <h1 className="text-6xl font-bold text-white mb-4 bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
              RTAPS
            </h1>
            <p className="text-xl text-gray-300">
              Real-Time Adaptive Procedure System
            </p>
            <div className="mt-4 h-1 w-24 bg-gradient-to-r from-purple-400 to-pink-400 mx-auto rounded-full"></div>
          </div>

          {!showUserForm ? (
            /* User Type Selection */
            <div className="space-y-6">
              <div className="text-center mb-8">
                <h2 className="text-2xl font-semibold text-white mb-2">
                  Welcome to RTAPS
                </h2>
                <p className="text-gray-400">
                  Please select your access type
                </p>
              </div>

              <div className="space-y-4">
                <button
                  onClick={() => setShowUserForm(true)}
                  className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold py-4 px-6 rounded-xl transition-all duration-300 transform hover:scale-105 hover:shadow-2xl shadow-lg"
                >
                  <div className="flex items-center justify-center space-x-3">
                    <div className="w-8 h-8 bg-white bg-opacity-20 rounded-full flex items-center justify-center">
                      <span className="text-lg">👤</span>
                    </div>
                    <div className="text-left">
                      <div className="text-lg">Participant</div>
                      <div className="text-sm opacity-90">Start a procedure session</div>
                    </div>
                  </div>
                </button>

                <button
                  onClick={handleAdminAccess}
                  className="w-full bg-gradient-to-r from-slate-600 to-slate-700 hover:from-slate-700 hover:to-slate-800 text-white font-semibold py-4 px-6 rounded-xl transition-all duration-300 transform hover:scale-105 hover:shadow-2xl shadow-lg"
                >
                  <div className="flex items-center justify-center space-x-3">
                    <div className="w-8 h-8 bg-white bg-opacity-20 rounded-full flex items-center justify-center">
                      <span className="text-lg">⚙️</span>
                    </div>
                    <div className="text-left">
                      <div className="text-lg">Administrator</div>
                      <div className="text-sm opacity-90">Access analytics and management</div>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          ) : !userType ? (
            /* User Type Selection (New vs Returning) */
            <div className="space-y-6">
              <div className="text-center mb-8">
                <h2 className="text-2xl font-semibold text-white mb-2">
                  Participant Access
                </h2>
                <p className="text-gray-400">
                  Are you a new or returning participant?
                </p>
              </div>

              <div className="space-y-4">
                <button
                  onClick={() => setUserType('new')}
                  className="w-full bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white font-semibold py-4 px-6 rounded-xl transition-all duration-300 transform hover:scale-105 hover:shadow-2xl shadow-lg"
                >
                  <div className="flex items-center justify-center space-x-3">
                    <div className="w-8 h-8 bg-white bg-opacity-20 rounded-full flex items-center justify-center">
                      <span className="text-lg">✨</span>
                    </div>
                    <div className="text-left">
                      <div className="text-lg">New Participant</div>
                      <div className="text-sm opacity-90">Create a new account</div>
                    </div>
                  </div>
                </button>

                <button
                  onClick={() => setUserType('returning')}
                  className="w-full bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700 text-white font-semibold py-4 px-6 rounded-xl transition-all duration-300 transform hover:scale-105 hover:shadow-2xl shadow-lg"
                >
                  <div className="flex items-center justify-center space-x-3">
                    <div className="w-8 h-8 bg-white bg-opacity-20 rounded-full flex items-center justify-center">
                      <span className="text-lg">🔄</span>
                    </div>
                    <div className="text-left">
                      <div className="text-lg">Returning Participant</div>
                      <div className="text-sm opacity-90">Sign in with existing username</div>
                    </div>
                  </div>
                </button>

                <button
                  onClick={() => setShowUserForm(false)}
                  className="w-full bg-gray-600 hover:bg-gray-700 text-white font-medium py-3 px-6 rounded-lg transition-colors duration-200"
                >
                  ← Back to Main Menu
                </button>
              </div>
            </div>
          ) : (
            /* Participant Registration/Login Form */
            <div className="bg-white bg-opacity-10 backdrop-blur-lg rounded-2xl p-8 shadow-2xl border border-white border-opacity-20">
              <div className="text-center mb-6">
                <h2 className="text-2xl font-semibold text-white mb-2">
                  {userType === 'new' ? 'Create New Account' : 'Sign In'}
                </h2>
                <p className="text-gray-300">
                  {userType === 'new' 
                    ? 'Choose a username to create your account' 
                    : 'Enter your username to sign in'
                  }
                </p>
              </div>

              <form onSubmit={handleUserSubmit} className="space-y-6">
                {/* Username Input */}
                <div>
                  <label className="block text-sm font-medium text-white mb-2">
                    {userType === 'new' ? 'Choose a Username *' : 'Enter Your Username *'}
                  </label>
                  <div className="relative">
                    <input
                      type="text"
                      value={username}
                      onChange={(e) => {
                        setUsername(e.target.value);
                        setUsernameError(''); // Clear error when typing
                      }}
                      className={`w-full px-4 py-3 pr-12 bg-white bg-opacity-10 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent ${
                        usernameError ? 'border-red-400' : 
                        (userType === 'new' && availabilityStatus === 'available') ? 'border-green-400' :
                        (userType === 'new' && availabilityStatus === 'taken') ? 'border-red-400' :
                        (userType === 'returning' && availabilityStatus === 'found') ? 'border-green-400' :
                        (userType === 'returning' && availabilityStatus === 'not-found') ? 'border-red-400' : 'border-white border-opacity-20'
                      }`}
                      placeholder={userType === 'new' ? "Enter your username (e.g., johnsmith, rtaps)" : "Enter your existing username"}
                      required
                    />
                    
                    {/* Availability Indicator */}
                    <div className="absolute right-3 top-1/2 transform -translate-y-1/2">
                      {isCheckingAvailability && (
                        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-purple-400"></div>
                      )}
                      {!isCheckingAvailability && userType === 'new' && availabilityStatus === 'available' && (
                        <div className="text-green-400">✓</div>
                      )}
                      {!isCheckingAvailability && userType === 'new' && availabilityStatus === 'taken' && (
                        <div className="text-red-400">✗</div>
                      )}
                      {!isCheckingAvailability && userType === 'returning' && availabilityStatus === 'found' && (
                        <div className="text-green-400">✓</div>
                      )}
                      {!isCheckingAvailability && userType === 'returning' && availabilityStatus === 'not-found' && (
                        <div className="text-red-400">✗</div>
                      )}
                    </div>
                  </div>
                  
                  {/* Username Status */}
                  {username && !isCheckingAvailability && (
                    <div className="mt-2">
                      {userType === 'new' && availabilityStatus === 'available' && (
                        <p className="text-sm text-green-300">✓ Username is available</p>
                      )}
                      {userType === 'new' && availabilityStatus === 'taken' && (
                        <p className="text-sm text-red-300">✗ Username is already taken</p>
                      )}
                      {userType === 'returning' && availabilityStatus === 'found' && (
                        <p className="text-sm text-green-300">✓ Welcome back! Username found</p>
                      )}
                      {userType === 'returning' && availabilityStatus === 'not-found' && (
                        <p className="text-sm text-red-300">✗ Username not found</p>
                      )}
                    </div>
                  )}
                  
                  {/* Error Message */}
                  {usernameError && (
                    <div className="mt-2 bg-red-600 bg-opacity-20 border border-red-400 border-opacity-30 rounded-lg p-3">
                      <p className="text-sm text-red-300">{usernameError}</p>
                    </div>
                  )}
                  
                  {/* Help Text */}
                  <p className="mt-1 text-xs text-gray-300">
                    3-20 characters, letters, numbers, hyphens, and underscores only
                  </p>
                </div>

                {/* Buttons */}
                <div className="flex space-x-4 pt-4">
                  <button
                    type="button"
                    onClick={() => {
                      setUserType('');
                      setUsername('');
                      setAvailabilityStatus('');
                      setUsernameError('');
                    }}
                    className="flex-1 px-4 py-3 bg-gray-600 hover:bg-gray-700 text-white font-medium rounded-lg transition-colors duration-200"
                  >
                    Back
                  </button>
                  <button
                    type="submit"
                    disabled={isLoading || (userType === 'new' && availabilityStatus !== 'available') || (userType === 'returning' && availabilityStatus !== 'found')}
                    className="flex-1 px-4 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-medium rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isLoading ? (
                      <div className="flex items-center justify-center">
                        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
                        {userType === 'new' ? 'Creating...' : 'Signing in...'}
                      </div>
                    ) : (
                      userType === 'new' ? 'Create Account' : 'Sign In'
                    )}
                  </button>
                </div>
              </form>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default LandingPage;
