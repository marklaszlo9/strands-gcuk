# cognito_auth.py
import boto3
import os
from botocore.exceptions import ClientError

class CognitoAuth:
    def __init__(self):
        self.client = boto3.client('cognito-idp', region_name=os.environ.get('AWS_REGION','us-west-2'))
        # Get these values from environment variables
        self.user_pool_id = os.environ.get('COGNITO_USER_POOL_ID','<user pool ID>') #['COGNITO_USER_POOL_ID']
        self.client_id = os.environ.get('COGNITO_CLIENT_ID','<Cognito Client ID>') #['COGNITO_CLIENT_ID']

        print("user_pool_id :" + self.user_pool_id)
        print("client_id :" + self.client_id)
        
        if not self.user_pool_id or not self.client_id:
            print("Warning: COGNITO_USER_POOL_ID or COGNITO_CLIENT_ID environment variables are not set")

    def authenticate_user(self, email, password):
        try:
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': email, # Use email as username
                    'PASSWORD': password
                }
            )
            return response['AuthenticationResult']['AccessToken']
        except ClientError as e:
            print(f"Error authenticating user: {e}")
            return None

    def get_user_groups(self, email):  # Use email parameter
        try:
            response = self.client.admin_list_groups_for_user(
                Username=email, # Use email as username
                UserPoolId=self.user_pool_id
            )
            return [group['GroupName'] for group in response['Groups']]
        except ClientError as e:
            print(f"Error getting user groups: {e}")
            return []

    def create_user_pool(self):
        try:
            response = self.client.create_user_pool(
                PoolName='AuroraGPTUserPool',
                Policies={
                    'PasswordPolicy': {
                        'MinimumLength': 8,
                        'RequireUppercase': True,
                        'RequireLowercase': True,
                        'RequireNumbers': True,
                        'RequireSymbols': True
                    }
                },
                Schema=[
                    {
                        'Name': 'email',
                        'AttributeDataType': 'String',
                        'Required': True,
                        'Mutable': True
                    }
                ],
                AutoVerifiedAttributes=['email']
            )
            return response['UserPool']['Id']
        except ClientError as e:
            print(f"Error creating user pool: {e}")
            return None

    def create_user_pool_client(self):
        try:
            response = self.client.create_user_pool_client(
                UserPoolId=self.user_pool_id,
                ClientName='AuroraGPTClient',
                GenerateSecret=False,
                ExplicitAuthFlows=['ALLOW_USER_PASSWORD_AUTH', 'ALLOW_REFRESH_TOKEN_AUTH']
            )
            return response['UserPoolClient']['ClientId']
        except ClientError as e:
            print(f"Error creating user pool client: {e}")
            return None

    def create_group(self, group_name, description):
        try:
            self.client.create_group(
                GroupName=group_name,
                UserPoolId=self.user_pool_id,
                Description=description
            )
            return True
        except ClientError as e:
            print(f"Error creating group {group_name}: {e}")
            return False

    def create_user(self, username, email, password, group_name):
        try:
            # Create user
            self.client.sign_up(
                ClientId=self.client_id,
                Username=username,
                Password=password,
                UserAttributes=[
                    {'Name': 'email', 'Value': email}
                ]
            )
            
            # Confirm user (admin)
            self.client.admin_confirm_sign_up(
                UserPoolId=self.user_pool_id,
                Username=username
            )
            
            # Add user to group
            self.client.admin_add_user_to_group(
                UserPoolId=self.user_pool_id,
                Username=username,
                GroupName=group_name
            )
            return True
        except ClientError as e:
            print(f"Error creating user {username}: {e}")
            return False
