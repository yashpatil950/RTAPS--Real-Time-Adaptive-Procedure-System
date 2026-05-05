## RTAPS Data Flow and Deployment Architecture

This document describes how data flows through the RTAPS web application and where it is stored. It also lists the AWS services used and highlights key security considerations.

### High-Level Architecture

```text
+-----------------------+            +-------------------------+
|  End User Browser     |  HTTPS     |  Amazon CloudFront CDN  |
|  (React Single Page   | <------->  |  (TLS termination, CDN) |
|  Application)         |            +-----------+-------------+
+-----------+-----------+                        |
            ^                                     |
            |  HTML/CSS/JS (static assets)        |
            |                                     v
            |                          +---------------------------+
            |                          | Amazon S3 (Static Hosting)|
            |                          | React build artifacts     |
            |                          +---------------------------+
            |
            |  JSON over HTTPS
            v
+-----------+-----------+            +----------------------------+
|  Frontend SPA         |  calls     | Amazon API Gateway |
|  (fetch to API)       +----------> +  /prod stage               |
+-----------------------+            +-------------+--------------+
                                                      |
                                                      | invokes
                                                      v
                                           +-----------------------+
                                           | AWS Lambda Functions  |
                                           +-----------+-----------+
                                                       |
                                                       | SDK calls
                                                       v
                                           +-----------------------+
                                           | Amazon DynamoDB       |
                                           +-----------------------+
```

### End-to-End Data Flow (User Journey)

- **Static content delivery**: The React app is built and uploaded to **Amazon S3**. **Amazon CloudFront** serves these assets over HTTPS.
- **User actions in SPA**: The SPA makes REST calls to the backend via **Amazon API Gateway** (`/prod` stage).
- **Request processing**: API Gateway routes requests to **AWS Lambda** functions:
- **Data persistence**: Lambda functions read/write JSON records in **Amazon DynamoDB** tables:
- **Responses**: Lambda returns JSON to API Gateway, which returns responses to the SPA over HTTPS.

### Data Storage Locations

- **Amazon DynamoDB**
  - Primary data store for users and sessions

- **Amazon S3 (Static Website Bucket)**
  - Stores built frontend assets (HTML/CSS/JS/images)
  - Public-read for website content

### AWS Services Used

- **Amazon S3**: Static website hosting for the React build
- **Amazon CloudFront**: CDN and HTTPS in front of S3 (primary public endpoint)
- **Amazon API Gateway (REST API)**: Public API front door for the SPA
- **AWS Lambda**: Serverless compute for user and session APIs
- **Amazon DynamoDB**: Persistent storage for users and sessions
- **AWS IAM**: Execution roles, S3 bucket policy, and service permissions


### Security and Data Handling

- **Transport security**
  - CloudFront provides HTTPS for end users; the SPA communicates with API Gateway over HTTPS.

- **Public content controls**
  - S3 bucket hosting the SPA is configured for public read.

- **API access**
  - Current Lambda handlers do not enforce authentication/authorization.

- **Data at rest**
  - DynamoDB offers server-side encryption by default.

- **Identity and permissions**
  - Lambda functions use IAM execution roles to access DynamoDB.




