import json
import boto3
from typing import Optional
from breez_sdk_liquid import (
    LiquidNetwork,
    PayAmount,
    ConnectRequest,
    PrepareSendRequest,
    SendPaymentRequest,
    PrepareReceiveRequest,
    ReceivePaymentRequest,
    EventListener,
    SdkEvent,
    connect,
    default_config,
    PaymentMethod,
    ListPaymentsRequest
)
import time
import logging
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()
app = APIGatewayRestResolver()

class SdkListener(EventListener):
    def __init__(self):
        self.synced = False
        self.paid = []

    def on_event(self, event):
        if isinstance(event, SdkEvent.SYNCED):
            self.synced = True
        if isinstance(event, SdkEvent.PAYMENT_SUCCEEDED):
            if event.details.destination:
                self.paid.append(event.details.destination)
    
    def is_paid(self, destination: str):
        return destination in self.paid

class PaymentHandler:
    def __init__(self):
        self.breez_api_key = self._get_ssm_parameter('/breez-nodeless/api_key')
        self.seed_phrase = self._get_ssm_parameter('/breez-nodeless/seed_phrase')
        
        if not self.breez_api_key:
            raise Exception("Missing Breez API key in Parameter Store")
        if not self.seed_phrase:
            raise Exception("Missing seed phrase in Parameter Store")
        
        logger.info("Retrieved encrypted parameters successfully")
        
        config = default_config(LiquidNetwork.MAINNET, self.breez_api_key)
        config.working_dir = '/tmp'
        connect_request = ConnectRequest(config=config, mnemonic=self.seed_phrase)
        self.instance = connect(connect_request)
        self.listener = SdkListener()
        self.instance.add_event_listener(self.listener)
        
    def _get_ssm_parameter(self, param_name: str) -> str:
        """Get an encrypted parameter from AWS Systems Manager Parameter Store"""
        logger.info(f"Retrieving encrypted parameter: {param_name}")
        ssm = boto3.client('ssm')
        try:
            response = ssm.get_parameter(
                Name=param_name,
                WithDecryption=True
            )
            return response['Parameter']['Value']
        except ssm.exceptions.ParameterNotFound:
            logger.error(f"Parameter {param_name} not found in Parameter Store")
            raise Exception(f"Parameter {param_name} not found in Parameter Store")
        except Exception as e:
            logger.error(f"Failed to get parameter {param_name}: {str(e)}", exc_info=True)
            raise Exception(f"Failed to get parameter {param_name}: {str(e)}")
    
    def wait_for_sync(self, timeout_seconds: int = 30):
        """Wait for the SDK to sync before proceeding."""
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            if self.listener.synced:
                return True
            time.sleep(1)
        raise Exception("Sync timeout: SDK did not sync within the allocated time.")

    def wait_for_payment(self, destination: str, timeout_seconds: int = 60) -> bool:
        """Wait for payment to complete or timeout"""
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            if self.listener.is_paid(destination):
                return True
            time.sleep(1)
        return False

    def list_payments(self, params: dict = None) -> dict:
        try:
            self.wait_for_sync()  # Ensure sync before executing
            from_ts = int(params.get('from_timestamp')) if params and params.get('from_timestamp') is not None else None
            to_ts = int(params.get('to_timestamp')) if params and params.get('to_timestamp') is not None else None
            offset = int(params.get('offset')) if params and params.get('offset') is not None else None
            limit = int(params.get('limit')) if params and params.get('limit') is not None else None
            
            req = ListPaymentsRequest(
                from_timestamp=from_ts,
                to_timestamp=to_ts,
                offset=offset,
                limit=limit
            )
            payments = self.instance.list_payments(req)
            payment_list = []
            for payment in payments:
                payment_dict = {
                    'timestamp': payment.timestamp,
                    'amount_sat': payment.amount_sat,
                    'fees_sat': payment.fees_sat,
                    'payment_type': str(payment.payment_type),
                    'status': str(payment.status),
                    'details': str(payment.details),
                    'destination': payment.destination,
                    'tx_id': payment.tx_id
                }
                payment_list.append(payment_dict)
            
            # apply offset, limit and timestamp filters
            print(f"payment_list: {payment_list}")
            filtered_payments = []
            for payment in payment_list:
                if from_ts and payment['timestamp'] < from_ts:
                    continue
                if to_ts and payment['timestamp'] > to_ts:
                    continue
                if offset and offset > 0:
                    offset -= 1
                    continue
                filtered_payments.append(payment)
            
            # apply limit
            if limit and limit < len(filtered_payments):
                filtered_payments = filtered_payments[:limit]
            
            # apply offset
            if offset and offset > 0:
                filtered_payments = payment_list[offset:]

            if not (offset or limit or from_ts or to_ts):
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'payments': payment_list
                    })
                }
            # apply limit
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'payments': filtered_payments
                })
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': str(e)})
            }

    def receive_payment(self, amount: int, payment_method: str = 'LIGHTNING') -> dict:
        try:
            self.wait_for_sync()  # Ensure sync before executing
            prepare_req = PrepareReceiveRequest(getattr(PaymentMethod, payment_method), amount)
            prepare_res = self.instance.prepare_receive_payment(prepare_req)
            req = ReceivePaymentRequest(prepare_res)
            res = self.instance.receive_payment(req)
            
            # Return the invoice details immediately
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'destination': res.destination,
                    'fees_sat': prepare_res.fees_sat
                })
            }
        except Exception as e:
            return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

    def send_payment(self, destination: str, amount: Optional[int] = None, drain: bool = False) -> dict:
        try:
            self.wait_for_sync()  # Ensure sync before executing
            pay_amount = PayAmount.DRAIN if drain else PayAmount.RECEIVER(amount) if amount else None
            prepare_req = PrepareSendRequest(destination, pay_amount)
            prepare_res = self.instance.prepare_send_payment(prepare_req)
            req = SendPaymentRequest(prepare_res)
            res = self.instance.send_payment(req)
            return {'statusCode': 200, 'body': json.dumps({'payment_status': 'success', 'destination': res.payment.destination, 'fees_sat': prepare_res.fees_sat})}
        except Exception as e:
            return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

def validate_api_key(event):
    """Validate the API key from the request headers"""
    try:
        logger.info("Headers received: %s", json.dumps(event.get('headers', {})))
        api_key = event.get('headers', {}).get('x-api-key')
        if not api_key:
            logger.warning("No API key provided in request headers")
            return False
        
        logger.info("API key found in headers")
        
        # Get the stored API key from SSM
        ssm = boto3.client('ssm')
        try:
            stored_key = ssm.get_parameter(
                Name='/breez-nodeless/api_secret',
                WithDecryption=True
            )['Parameter']['Value']
            logger.info("Successfully retrieved stored API key from SSM")
            
            # Compare keys (safely log length but not the actual keys)
            keys_match = api_key == stored_key
            logger.info("API key validation result: %s (lengths: request=%d, stored=%d)", 
                       keys_match, len(api_key), len(stored_key))
            return keys_match
            
        except ssm.exceptions.ParameterNotFound:
            logger.error("SSM parameter /breez-nodeless/api_secret not found")
            return False
    except Exception as e:
        logger.error(f"Error validating API key: {str(e)}", exc_info=True)
        return False

@app.get("/list_payments")
@tracer.capture_method
def list_payments():
    try:
        if not validate_api_key(app.current_event):
            return {"statusCode": 401, "body": json.dumps({"error": "Unauthorized"})}
            
        logger.info("Processing list_payments request")
        handler = PaymentHandler()
        return handler.list_payments(app.current_event.query_string_parameters or {})
    except Exception as e:
        logger.error(f"Error listing payments: {str(e)}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

@app.post("/receive_payment")
@tracer.capture_method
def receive_payment():
    try:
        if not validate_api_key(app.current_event):
            return {"statusCode": 401, "body": json.dumps({"error": "Unauthorized"})}
            
        body = app.current_event.json_body
        logger.info(f"Processing receive_payment request with body: {body}")
        
        handler = PaymentHandler()
        return handler.receive_payment(
            amount=body['amount'],
            payment_method=body.get('method', 'LIGHTNING')
        )
    except Exception as e:
        logger.error(f"Error receiving payment: {str(e)}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

@app.post("/send_payment")
@tracer.capture_method
def send_payment():
    try:
        if not validate_api_key(app.current_event):
            return {"statusCode": 401, "body": json.dumps({"error": "Unauthorized"})}
            
        body = app.current_event.json_body
        logger.info(f"Processing send_payment request with body: {body}")
        
        handler = PaymentHandler()
        return handler.send_payment(
            destination=body['destination'],
            amount=body.get('amount'),
            drain=body.get('drain', False)
        )
    except Exception as e:
        logger.error(f"Error sending payment: {str(e)}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

# Add this to your lambda_function.py file

@app.get("/checkout")
@tracer.capture_method
def serve_checkout():
    """Redirect to S3-hosted checkout page with payment parameters"""
    try:
        # Get query parameters (amount, order_id, etc.)
        params = app.current_event.query_string_parameters or {}
        
        # API key validation is optional for checkout page (can be passed as param)
        validate_request = params.get('require_auth', 'false').lower() == 'true'
        if validate_request and not validate_api_key(app.current_event):
            return {"statusCode": 401, "body": json.dumps({"error": "Unauthorized"})}
            
        logger.info(f"Processing checkout redirect with params: {params}")
        
        # Get S3 bucket URL from environment variable or parameter store
        ssm = boto3.client('ssm')
        checkout_base_url = "https://lightning-checkout.s3-website-us-east-1.amazonaws.com/checkout.html"
        """
        try:
            checkout_base_url = ssm.get_parameter(
                Name='/breez-nodeless/checkout_url'
            )['Parameter']['Value']
        except ssm.exceptions.ParameterNotFound:
            # Default to environment variable or hardcoded URL if parameter not found
            checkout_base_url = os.environ.get(
                'CHECKOUT_BASE_URL', 
                'https://your-s3-bucket-name.s3-website-region.amazonaws.com/checkout.html'
            )
        """
        # Build the checkout URL with query parameters
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        redirect_url = f"{checkout_base_url}?{query_string}" if query_string else checkout_base_url
        
        # Return redirect response
        return {
            "statusCode": 302,
            "headers": {
                "Location": redirect_url,
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            },
            "body": ""
        }
    except Exception as e:
        logger.error(f"Error serving checkout: {str(e)}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)


