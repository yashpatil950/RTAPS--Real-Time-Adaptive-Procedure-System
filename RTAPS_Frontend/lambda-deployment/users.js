// AWS Lambda function for user management
const AWS = require('aws-sdk');
const dynamodb = new AWS.DynamoDB.DocumentClient();

const USERS_TABLE = 'rtaps-users';

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
    const { httpMethod, pathParameters, body, queryStringParameters } = event;
    const userId = pathParameters?.userId;
    const userData = body ? JSON.parse(body) : null;

    let result;

    switch (httpMethod) {
      case 'GET':
        if (userId) {
          result = await getUser(userId);
        } else {
          result = await getUsers();
        }
        break;

      case 'POST':
        result = await createUser(userData);
        break;

      case 'PUT':
        if (!userId) {
          throw new Error('User ID is required for update');
        }
        result = await updateUser(userId, userData);
        break;

      case 'DELETE':
        if (!userId) {
          throw new Error('User ID is required for deletion');
        }
        result = await deleteUser(userId);
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

// Get all users
async function getUsers() {
  const params = {
    TableName: USERS_TABLE,
    FilterExpression: 'isActive = :isActive',
    ExpressionAttributeValues: {
      ':isActive': true
    }
  };

  const result = await dynamodb.scan(params).promise();
  return {
    users: result.Items || [],
    count: result.Count || 0
  };
}

// Get single user
async function getUser(userId) {
  const params = {
    TableName: USERS_TABLE,
    Key: { userId }
  };

  const result = await dynamodb.get(params).promise();
  
  if (!result.Item) {
    throw new Error('User not found');
  }

  return { user: result.Item };
}

// Create new user
async function createUser(userData) {
  const { username, role = 'user' } = userData;

  // Check if username already exists
  const existingUser = await getUserByUsername(username);
  if (existingUser) {
    throw new Error('Username already exists');
  }

  // Generate user ID
  const userId = await generateUserId();

  const user = {
    userId,
    username,
    role,
    createdAt: new Date().toISOString(),
    lastLogin: new Date().toISOString(),
    isActive: true
  };

  const params = {
    TableName: USERS_TABLE,
    Item: user
  };

  await dynamodb.put(params).promise();
  return { user };
}

// Update user
async function updateUser(userId, userData) {
  const updateExpression = [];
  const expressionAttributeNames = {};
  const expressionAttributeValues = {};

  // Build update expression dynamically
  Object.keys(userData).forEach(key => {
    if (key !== 'userId') {
      updateExpression.push(`#${key} = :${key}`);
      expressionAttributeNames[`#${key}`] = key;
      expressionAttributeValues[`:${key}`] = userData[key];
    }
  });

  if (updateExpression.length === 0) {
    throw new Error('No fields to update');
  }

  const params = {
    TableName: USERS_TABLE,
    Key: { userId },
    UpdateExpression: `SET ${updateExpression.join(', ')}`,
    ExpressionAttributeNames: expressionAttributeNames,
    ExpressionAttributeValues: expressionAttributeValues,
    ReturnValues: 'ALL_NEW'
  };

  const result = await dynamodb.update(params).promise();
  return { user: result.Attributes };
}

// Delete user (soft delete)
async function deleteUser(userId) {
  const params = {
    TableName: USERS_TABLE,
    Key: { userId },
    UpdateExpression: 'SET isActive = :isActive, deletedAt = :deletedAt',
    ExpressionAttributeValues: {
      ':isActive': false,
      ':deletedAt': new Date().toISOString()
    },
    ReturnValues: 'ALL_NEW'
  };

  const result = await dynamodb.update(params).promise();
  return { user: result.Attributes };
}

// Helper function to get user by username
async function getUserByUsername(username) {
  const params = {
    TableName: USERS_TABLE,
    IndexName: 'username-index',
    KeyConditionExpression: 'username = :username',
    ExpressionAttributeValues: {
      ':username': username
    }
  };

  const result = await dynamodb.query(params).promise();
  return result.Items?.[0] || null;
}

// Helper function to generate unique user ID
async function generateUserId() {
  const params = {
    TableName: USERS_TABLE,
    ProjectionExpression: 'userId',
    FilterExpression: 'begins_with(userId, :prefix)',
    ExpressionAttributeValues: {
      ':prefix': 'P'
    }
  };

  const result = await dynamodb.scan(params).promise();
  const maxId = result.Items.reduce((max, item) => {
    const id = parseInt(item.userId.substring(1));
    return id > max ? id : max;
  }, 0);

  return `P${maxId + 1}`;
}
