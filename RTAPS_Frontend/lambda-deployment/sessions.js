// AWS Lambda function for session management
const AWS = require('aws-sdk');
const dynamodb = new AWS.DynamoDB.DocumentClient();

const SESSIONS_TABLE = 'rtaps-sessions';

// CORS headers
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type,Authorization',
  'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
};

exports.handler = async (event) => {
  console.log('Event:', JSON.stringify(event, null, 2));

  // Handle CORS preflight
  if (event.httpMethod === 'OPTIONS') {
    return {
      statusCode: 200,
      headers: corsHeaders,
      body: JSON.stringify({ message: 'CORS preflight' })
    };
  }

  try {
    const { httpMethod, pathParameters, queryStringParameters, body } = event;
    const sessionId = pathParameters?.sessionId;
    const sessionData = body ? JSON.parse(body) : null;

    let result;

    switch (httpMethod) {
      case 'GET':
        if (sessionId) {
          result = await getSession(sessionId);
        } else {
          const userId = queryStringParameters?.userId;
          result = await getSessions(userId);
        }
        break;

      case 'POST':
        result = await createSession(sessionData);
        break;

      case 'PUT':
        if (!sessionId) {
          throw new Error('Session ID is required for update');
        }
        result = await updateSession(sessionId, sessionData);
        break;

      case 'DELETE':
        if (!sessionId) {
          throw new Error('Session ID is required for deletion');
        }
        result = await deleteSession(sessionId);
        break;

      default:
        throw new Error(`Unsupported method: ${httpMethod}`);
    }

    return {
      statusCode: 200,
      headers: corsHeaders,
      body: JSON.stringify(result)
    };

  } catch (error) {
    console.error('Error:', error);
    return {
      statusCode: 500,
      headers: corsHeaders,
      body: JSON.stringify({
        error: error.message || 'Internal server error'
      })
    };
  }
};

// Get sessions (optionally filtered by userId)
async function getSessions(userId = null) {
  if (userId) {
    // Query by participant ID on GSI, sorted by completedAt descending
    const queryParams = {
      TableName: SESSIONS_TABLE,
      IndexName: 'participant-sessions',
      KeyConditionExpression: 'participantId = :participantId',
      ExpressionAttributeValues: {
        ':participantId': userId
      },
      ScanIndexForward: false
    };
    const result = await dynamodb.query(queryParams).promise();
    return {
      sessions: result.Items || [],
      count: result.Count || 0
    };
  }

  // Scan all sessions (no sort key available for Scan)
  const scanParams = {
    TableName: SESSIONS_TABLE
  };
  const result = await dynamodb.scan(scanParams).promise();

  return {
    sessions: result.Items || [],
    count: result.Count || 0
  };
}

// Get single session
async function getSession(sessionId) {
  // For single session lookup, we'll scan since we need to find by sessionId only
  const params = {
    TableName: SESSIONS_TABLE,
    FilterExpression: 'sessionId = :sessionId',
    ExpressionAttributeValues: {
      ':sessionId': sessionId
    }
  };

  const result = await dynamodb.scan(params).promise();
  
  if (!result.Items || result.Items.length === 0) {
    throw new Error('Session not found');
  }

  return { session: result.Items[0] };
}

// Create new session
async function createSession(sessionData) {
  const {
    participantId,
    participantUsername,
    procedureId,
    procedureName = null,
    totalTimeSec,
    steps = [],
    trainNumber = null,
    metadata = {}
  } = sessionData;

  const sessionId = generateSessionId();
  const completedAt = new Date().toISOString();

  const session = {
    sessionId,
    participantId,
    participantUsername,
    procedureId,
    procedureName,
    completedAt,
    totalTimeSec,
    steps,
    trainNumber,
    metadata: {
      ...metadata,
      createdAt: completedAt,
      version: '1.0'
    }
  };

  const params = {
    TableName: SESSIONS_TABLE,
    Item: session
  };

  await dynamodb.put(params).promise();
  return { session };
}

// Update session
async function updateSession(sessionId, sessionData) {
  // Find the session first
  const existingSession = await getSession(sessionId);
  const session = existingSession.session;

  const updateExpression = [];
  const expressionAttributeNames = {};
  const expressionAttributeValues = {};

  // Build update expression dynamically
  Object.keys(sessionData).forEach(key => {
    if (key !== 'sessionId' && key !== 'completedAt') {
      updateExpression.push(`#${key} = :${key}`);
      expressionAttributeNames[`#${key}`] = key;
      expressionAttributeValues[`:${key}`] = sessionData[key];
    }
  });

  if (updateExpression.length === 0) {
    throw new Error('No fields to update');
  }

  // Add updatedAt timestamp
  updateExpression.push('#updatedAt = :updatedAt');
  expressionAttributeNames['#updatedAt'] = 'updatedAt';
  expressionAttributeValues[':updatedAt'] = new Date().toISOString();

  const params = {
    TableName: SESSIONS_TABLE,
    Key: { 
      sessionId: session.sessionId,
      completedAt: session.completedAt
    },
    UpdateExpression: `SET ${updateExpression.join(', ')}`,
    ExpressionAttributeNames: expressionAttributeNames,
    ExpressionAttributeValues: expressionAttributeValues,
    ReturnValues: 'ALL_NEW'
  };

  const result = await dynamodb.update(params).promise();
  return { session: result.Attributes };
}

// Delete session
async function deleteSession(sessionId) {
  // Find the session first
  const existingSession = await getSession(sessionId);
  const session = existingSession.session;

  const params = {
    TableName: SESSIONS_TABLE,
    Key: { 
      sessionId: session.sessionId,
      completedAt: session.completedAt
    }
  };

  await dynamodb.delete(params).promise();
  return { message: 'Session deleted successfully' };
}

// Helper function to generate unique session ID
function generateSessionId() {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substring(2, 8);
  return `sess_${timestamp}_${random}`;
}
