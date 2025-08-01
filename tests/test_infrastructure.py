"""
Tests for CloudFormation infrastructure template
"""
import json
import yaml
import pytest
from pathlib import Path


class TestInfrastructure:
    """Test cases for the CloudFormation template"""
    
    @classmethod
    def setup_class(cls):
        """Load the CloudFormation template"""
        template_path = Path(__file__).parent.parent / 'infrastructure' / 'frontend-infrastructure.yaml'
        with open(template_path, 'r') as f:
            cls.template = yaml.safe_load(f)
    
    def test_template_format_version(self):
        """Test CloudFormation template format version"""
        assert self.template['AWSTemplateFormatVersion'] == '2010-09-09'
    
    def test_template_description(self):
        """Test template has description"""
        assert 'Description' in self.template
        assert 'S3 + CloudFront + Lambda' in self.template['Description']
    
    def test_required_parameters(self):
        """Test required parameters are defined"""
        parameters = self.template.get('Parameters', {})
        
        # AgentRuntimeArn parameter
        assert 'AgentRuntimeArn' in parameters
        assert parameters['AgentRuntimeArn']['Type'] == 'String'
        assert 'Default' in parameters['AgentRuntimeArn']
    
    def test_s3_bucket_configuration(self):
        """Test S3 bucket is properly configured"""
        resources = self.template.get('Resources', {})
        
        # Check FrontendBucket exists
        assert 'FrontendBucket' in resources
        bucket = resources['FrontendBucket']
        
        assert bucket['Type'] == 'AWS::S3::Bucket'
        
        # Check website configuration
        properties = bucket['Properties']
        assert 'WebsiteConfiguration' in properties
        assert properties['WebsiteConfiguration']['IndexDocument'] == 'index.html'
        
        # Check CORS configuration
        assert 'CorsConfiguration' in properties
        cors_rules = properties['CorsConfiguration']['CorsRules']
        assert len(cors_rules) > 0
        assert 'GET' in cors_rules[0]['AllowedMethods']
    
    def test_lambda_function_configuration(self):
        """Test Lambda function is properly configured"""
        resources = self.template.get('Resources', {})
        
        # Check Lambda function exists
        assert 'AgentCoreProxyFunction' in resources
        lambda_func = resources['AgentCoreProxyFunction']
        
        assert lambda_func['Type'] == 'AWS::Lambda::Function'
        
        properties = lambda_func['Properties']
        assert properties['Runtime'] == 'python3.11'
        assert properties['Handler'] == 'agentcore_proxy.lambda_handler'
        assert properties['Timeout'] == 30
        
        # Check boto3 layer is included
        assert 'Layers' in properties
        layers = properties['Layers']
        assert len(layers) > 0
        assert 'boto3-latest' in layers[0]
        
        # Check environment variables
        assert 'Environment' in properties
        env_vars = properties['Environment']['Variables']
        assert 'AGENT_ARN' in env_vars
    
    def test_lambda_execution_role(self):
        """Test Lambda execution role has proper permissions"""
        resources = self.template.get('Resources', {})
        
        # Check execution role exists
        assert 'LambdaExecutionRole' in resources
        role = resources['LambdaExecutionRole']
        
        assert role['Type'] == 'AWS::IAM::Role'
        
        properties = role['Properties']
        
        # Check managed policies
        managed_policies = properties['ManagedPolicyArns']
        assert 'AWSLambdaBasicExecutionRole' in managed_policies[0]
        
        # Check custom policies
        policies = properties['Policies']
        assert len(policies) > 0
        
        agentcore_policy = policies[0]
        assert agentcore_policy['PolicyName'] == 'AgentCoreAccess'
        
        statements = agentcore_policy['PolicyDocument']['Statement']
        assert len(statements) > 0
        assert 'bedrock-agentcore:InvokeAgentRuntime' in statements[0]['Action']
    
    def test_api_gateway_configuration(self):
        """Test API Gateway is properly configured"""
        resources = self.template.get('Resources', {})
        
        # Check API Gateway exists
        assert 'ApiGateway' in resources
        api = resources['ApiGateway']
        assert api['Type'] == 'AWS::ApiGateway::RestApi'
        
        # Check API resource
        assert 'ApiResource' in resources
        resource = resources['ApiResource']
        assert resource['Type'] == 'AWS::ApiGateway::Resource'
        assert resource['Properties']['PathPart'] == 'agentcore'
        
        # Check POST method
        assert 'ApiMethod' in resources
        method = resources['ApiMethod']
        assert method['Type'] == 'AWS::ApiGateway::Method'
        assert method['Properties']['HttpMethod'] == 'POST'
        assert method['Properties']['Integration']['Type'] == 'AWS_PROXY'
        
        # Check OPTIONS method for CORS
        assert 'ApiOptionsMethod' in resources
        options_method = resources['ApiOptionsMethod']
        assert options_method['Type'] == 'AWS::ApiGateway::Method'
        assert options_method['Properties']['HttpMethod'] == 'OPTIONS'
    
    def test_lambda_api_gateway_permission(self):
        """Test Lambda has permission to be invoked by API Gateway"""
        resources = self.template.get('Resources', {})
        
        assert 'LambdaApiGatewayPermission' in resources
        permission = resources['LambdaApiGatewayPermission']
        
        assert permission['Type'] == 'AWS::Lambda::Permission'
        
        properties = permission['Properties']
        assert properties['Action'] == 'lambda:InvokeFunction'
        assert properties['Principal'] == 'apigateway.amazonaws.com'
        
        # Check SourceArn uses wildcard pattern
        source_arn = properties['SourceArn']
        assert '/*/*' in source_arn
    
    def test_cloudfront_distribution(self):
        """Test CloudFront distribution is properly configured"""
        resources = self.template.get('Resources', {})
        
        assert 'CloudFrontDistribution' in resources
        distribution = resources['CloudFrontDistribution']
        
        assert distribution['Type'] == 'AWS::CloudFront::Distribution'
        
        config = distribution['Properties']['DistributionConfig']
        
        # Check origins
        assert 'Origins' in config
        origins = config['Origins']
        assert len(origins) > 0
        
        # Check default cache behavior
        assert 'DefaultCacheBehavior' in config
        behavior = config['DefaultCacheBehavior']
        assert behavior['ViewerProtocolPolicy'] == 'redirect-to-https'
        
        # Check custom error responses for SPA
        assert 'CustomErrorResponses' in config
        error_responses = config['CustomErrorResponses']
        assert len(error_responses) >= 2  # Should handle 404 and 403
    
    def test_s3_bucket_policy(self):
        """Test S3 bucket policy allows public read access"""
        resources = self.template.get('Resources', {})
        
        assert 'FrontendBucketPolicy' in resources
        policy = resources['FrontendBucketPolicy']
        
        assert policy['Type'] == 'AWS::S3::BucketPolicy'
        
        policy_doc = policy['Properties']['PolicyDocument']
        statements = policy_doc['Statement']
        
        # Find the public read statement
        public_read_statement = None
        for statement in statements:
            if statement.get('Sid') == 'PublicReadGetObject':
                public_read_statement = statement
                break
        
        assert public_read_statement is not None
        assert public_read_statement['Effect'] == 'Allow'
        assert public_read_statement['Principal'] == '*'
        assert public_read_statement['Action'] == 's3:GetObject'
    
    def test_required_outputs(self):
        """Test template has required outputs"""
        outputs = self.template.get('Outputs', {})
        
        required_outputs = [
            'FrontendBucketName',
            'CloudFrontDistributionId',
            'CloudFrontDomainName',
            'FrontendURL',
            'ApiGatewayURL',
            'LambdaFunctionName'
        ]
        
        for output in required_outputs:
            assert output in outputs, f"Missing required output: {output}"
            assert 'Description' in outputs[output]
            assert 'Value' in outputs[output]
    
    def test_conditional_logic(self):
        """Test conditional logic for custom domain"""
        conditions = self.template.get('Conditions', {})
        
        assert 'HasCustomDomain' in conditions
        assert 'HasCertificate' in conditions
        
        # Check that conditions are used in CloudFront configuration
        resources = self.template.get('Resources', {})
        distribution = resources['CloudFrontDistribution']
        config = distribution['Properties']['DistributionConfig']
        
        # Aliases should use conditional logic
        assert 'Aliases' in config
        aliases = config['Aliases']
        assert '!If' in str(aliases) or aliases == {'Ref': 'AWS::NoValue'}
    
    def test_api_deployment_dependencies(self):
        """Test API Gateway deployment has proper dependencies"""
        resources = self.template.get('Resources', {})
        
        assert 'ApiDeployment' in resources
        deployment = resources['ApiDeployment']
        
        assert deployment['Type'] == 'AWS::ApiGateway::Deployment'
        
        # Check dependencies
        depends_on = deployment.get('DependsOn', [])
        assert 'ApiMethod' in depends_on
        assert 'ApiOptionsMethod' in depends_on
    
    def test_template_validation(self):
        """Test template is valid YAML and has required structure"""
        # Template should have required top-level keys
        required_keys = ['AWSTemplateFormatVersion', 'Description', 'Resources']
        for key in required_keys:
            assert key in self.template, f"Missing required key: {key}"
        
        # Resources should not be empty
        assert len(self.template['Resources']) > 0
        
        # All resources should have Type
        for resource_name, resource in self.template['Resources'].items():
            assert 'Type' in resource, f"Resource {resource_name} missing Type"


class TestDeploymentScripts:
    """Test deployment scripts"""
    
    def test_deploy_script_exists(self):
        """Test deployment script exists and is executable"""
        script_path = Path(__file__).parent.parent / 'deploy-frontend.sh'
        assert script_path.exists(), "deploy-frontend.sh script not found"
        
        # Check if script has execute permissions (on Unix systems)
        import stat
        if hasattr(stat, 'S_IXUSR'):
            file_stat = script_path.stat()
            assert file_stat.st_mode & stat.S_IXUSR, "deploy-frontend.sh is not executable"
    
    def test_update_script_exists(self):
        """Test update script exists and is executable"""
        script_path = Path(__file__).parent.parent / 'update-lambda.sh'
        assert script_path.exists(), "update-lambda.sh script not found"
        
        # Check if script has execute permissions (on Unix systems)
        import stat
        if hasattr(stat, 'S_IXUSR'):
            file_stat = script_path.stat()
            assert file_stat.st_mode & stat.S_IXUSR, "update-lambda.sh is not executable"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])