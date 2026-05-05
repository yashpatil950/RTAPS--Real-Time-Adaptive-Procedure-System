#!/bin/bash

# Test script to verify local development still works
echo "🧪 Testing local development environment..."

echo "📦 Installing dependencies..."
npm install

echo "🚀 Starting development server..."
echo "The app should open at http://localhost:3000"
echo "Press Ctrl+C to stop the server"
echo ""

npm start
