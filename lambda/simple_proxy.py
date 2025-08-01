"""
Simplified Lambda function for testing CORS
"""
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Simplified Lambda handler that always returns CORS headers
    """
    # CORS headers that should be included in ALL responses
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Max-Age': '86400'
    }
    
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Handle preflight OPTIONS request
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': ''
            }
        
        # Handle POST request
        if event.get('httpMethod') == 'POST':
            # Parse body
            body = event.get('body', '{}')
            try:
                data = json.loads(body)
                prompt = data.get('prompt', '')
            except json.JSONDecodeError:
                return {
                    'statusCode': 400,
                    'headers': {**cors_headers, 'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'Invalid JSON'})
                }
            
            # Return a simple response for now
            return {
                'statusCode': 200,
                'headers': {**cors_headers, 'Content-Type': 'application/json'},
                'body': json.dumps({
                    'response': f'Echo: {prompt}',
                    'sessionId': data.get('sessionId', 'test'),
                    'timestamp': context.aws_request_id
                })
            }
        
        # Handle other methods
        return {
            'statusCode': 405,
            'headers': {**cors_headers, 'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Method not allowed'})
        }
        
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {**cors_headers, 'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Internal server error: {str(e)}'})
        }