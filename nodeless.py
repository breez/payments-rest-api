import json
import os
import argparse
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
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
    ListPaymentsRequest,
    InputType, # Added for parse functionality
    SignMessageRequest, # Added for message signing
    CheckMessageRequest, # Added for message checking
    BuyBitcoinProvider, # Added for buy bitcoin
    PrepareBuyBitcoinRequest, # Added for buy bitcoin
    BuyBitcoinRequest, # Added for buy bitcoin
    PreparePayOnchainRequest, # Added for pay onchain
    PayOnchainRequest, # Added for pay onchain
    RefundRequest, # Added for refunds
    RefundableSwap, # Added for refunds
    FetchPaymentProposedFeesRequest, # Added for fee acceptance
    AcceptPaymentProposedFeesRequest, # Added for fee acceptance
    PaymentState, # Added for fee acceptance
    PaymentDetails, # Added for fee acceptance
    AssetMetadata, # Added for assets
    ExternalInputParser, # Added for parsers
    GetPaymentRequest, # Added for get payment
    ListPaymentDetails, # Added for list payments by details
    ReceiveAmount, # Ensure ReceiveAmount is in this list!

    # --- Imports for refined method signatures ---
    PrepareBuyBitcoinResponse,
    PrepareLnUrlPayResponse,
    PreparePayOnchainResponse,
    # Correct Imports for LNURL Data Objects
    LnUrlPayRequestData, # Corrected import for prepare_lnurl_pay
    LnUrlAuthRequestData, # Corrected import for lnurl_auth
    LnUrlWithdrawRequestData, # Corrected import for lnurl_withdraw
    # RefundableSwap already imported
    # --- End imports ---
)
import time
import logging
from pprint import pprint

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SdkListener(EventListener):
    """
    A listener class for handling Breez SDK events.

    This class extends the EventListener from breez_sdk_liquid and implements
    custom event handling logic, particularly for tracking successful payments
    and other key SDK events.
    """
    def __init__(self):
        self.synced = False
        self.paid = []
        self.refunded = [] # Added for tracking refunds
        self.payment_statuses = {} # Track statuses for better payment checking

    def on_event(self, event):
        """Handles incoming SDK events."""
        # Log all events at debug level
        logger.debug(f"Received SDK event: {event}")

        if isinstance(event, SdkEvent.SYNCED):
            self.synced = True
            logger.info("SDK SYNCED")
        elif isinstance(event, SdkEvent.PAYMENT_SUCCEEDED):
            details = event.details
            # Determine identifier based on payment type
            identifier = None
            if hasattr(details, 'destination') and details.destination:
                 identifier = details.destination
            elif hasattr(details, 'payment_hash') and details.payment_hash:
                 identifier = details.payment_hash

            if identifier:
                # Avoid duplicates if the same identifier can be seen multiple times
                if identifier not in self.paid:
                    self.paid.append(identifier)
                self.payment_statuses[identifier] = 'SUCCEEDED'
                logger.info(f"PAYMENT SUCCEEDED for identifier: {identifier}")
            else:
                logger.info("PAYMENT SUCCEEDED with no clear identifier.")

            logger.debug(f"Payment Succeeded Details: {details}") # Log full details at debug

        elif isinstance(event, SdkEvent.PAYMENT_FAILED):
            details = event.details
            # Determine identifier based on payment type
            identifier = None
            if hasattr(details, 'destination') and details.destination:
                 identifier = details.destination
            elif hasattr(details, 'payment_hash') and details.payment_hash:
                 identifier = details.payment_hash
            elif hasattr(details, 'swap_id') and details.swap_id:
                 identifier = details.swap_id # Add swap_id as potential identifier

            error = getattr(details, 'error', 'Unknown error')

            if identifier:
                 self.payment_statuses[identifier] = 'FAILED'
                 logger.error(f"PAYMENT FAILED for identifier: {identifier}, Error: {error}")
            else:
                 logger.error(f"PAYMENT FAILED with no clear identifier. Error: {error}")

            logger.debug(f"Payment Failed Details: {details}") # Log full details at debug

    def is_paid(self, destination: str) -> bool:
        """Checks if a payment to a specific destination has succeeded."""
        # Check both the old list and the status dictionary
        return destination in self.paid or self.payment_statuses.get(destination) == 'SUCCEEDED'

    def is_synced(self) -> bool:
        """Checks if the SDK is synced."""
        return self.synced

    def get_payment_status(self, identifier: str) -> Optional[str]:
        """
        Get the known status for a payment identified by destination, hash, or swap ID.
        Returns status string ('SUCCEEDED', 'FAILED', 'REFUNDED', 'PENDING', etc.) or None.
        """
        return self.payment_statuses.get(identifier)


class PaymentHandler:
    """
    A wrapper class for the Breez SDK Nodeless (Liquid implementation).

    This class handles SDK initialization, connection, and provides simplified
    methods for common payment and wallet operations.
    """
    def __init__(self, network: LiquidNetwork = LiquidNetwork.MAINNET, working_dir: str = '~/.breez-cli', asset_metadata: Optional[List[AssetMetadata]] = None, external_input_parsers: Optional[List[ExternalInputParser]] = None):
        """
        Initializes the PaymentHandler and connects to the Breez SDK.

        Args:
            network: The Liquid network to use (MAINNET or TESTNET).
            working_dir: The directory for SDK files.
            asset_metadata: Optional list of AssetMetadata for non-Bitcoin assets.
            external_input_parsers: Optional list of ExternalInputParser for custom input parsing.
        """
        logger.debug("Entering PaymentHandler.__init__")
        load_dotenv() # Load environment variables from .env

        self.breez_api_key = os.getenv('BREEZ_API_KEY')
        self.seed_phrase = os.getenv('BREEZ_SEED_PHRASE')

        if not self.breez_api_key:
            logger.error("BREEZ_API_KEY not found in environment variables.")
            raise Exception("Missing Breez API key in .env file or environment")
        if not self.seed_phrase:
            logger.error("BREEZ_SEED_PHRASE not found in environment variables.")
            raise Exception("Missing seed phrase in .env file or environment")

        logger.info("Retrieved credentials from environment successfully")

        config = default_config(network, self.breez_api_key)
        # Expand user path for working_dir
        config.working_dir = os.path.expanduser(working_dir)
        # Ensure working directory exists
        try:
            os.makedirs(config.working_dir, exist_ok=True)
            logger.debug(f"Ensured working directory exists: {config.working_dir}")
        except OSError as e:
             logger.error(f"Failed to create working directory {config.working_dir}: {e}")
             raise # Re-raise if directory creation fails

        if asset_metadata:
            config.asset_metadata = asset_metadata
            logger.info(f"Configured asset metadata: {asset_metadata}")

        if external_input_parsers:
            config.external_input_parsers = external_input_parsers
            logger.info(f"Configured external input parsers: {external_input_parsers}")

        connect_request = ConnectRequest(config=config, mnemonic=self.seed_phrase)

        try:
            self.instance = connect(connect_request)
            self.listener = SdkListener()
            # Add listener immediately after connecting
            self.instance.add_event_listener(self.listener)
            logger.info("Breez SDK connected successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to Breez SDK: {e}")
            # Re-raise the exception after logging
            raise

        logger.debug("Exiting PaymentHandler.__init__")


    def wait_for_sync(self, timeout_seconds: int = 30):
        """Wait for the SDK to sync before proceeding."""
        logger.debug(f"Entering wait_for_sync (timeout={timeout_seconds}s)")
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            if self.listener.is_synced():
                logger.debug("SDK synced.")
                logger.debug("Exiting wait_for_sync (synced)")
                return True
            time.sleep(0.5) # Shorter sleep for faster sync detection
        logger.error("Sync timeout: SDK did not sync within the allocated time.")
        logger.debug("Exiting wait_for_sync (timeout)")
        raise Exception(f"Sync timeout: SDK did not sync within {timeout_seconds} seconds.")

    def wait_for_payment(self, identifier: str, timeout_seconds: int = 60) -> bool:
        """
        Wait for payment to complete or timeout for a specific identifier
        (destination, hash, or swap ID).
        """
        logger.debug(f"Entering wait_for_payment (identifier={identifier}, timeout={timeout_seconds}s)")
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            status = self.listener.get_payment_status(identifier)
            if status == 'SUCCEEDED':
                logger.debug(f"Payment for {identifier} succeeded.")
                logger.debug("Exiting wait_for_payment (succeeded)")
                return True
            if status == 'FAILED':
                 logger.error(f"Payment for {identifier} failed during wait.")
                 logger.debug("Exiting wait_for_payment (failed)")
                 return False
            # Consider other final states like 'REFUNDED' if applicable
            if status == 'REFUNDED':
                logger.info(f"Swap for {identifier} was refunded during wait.")
                logger.debug("Exiting wait_for_payment (refunded)")
                return False

            time.sleep(1)
        logger.warning(f"Wait for payment for {identifier} timed out.")
        logger.debug("Exiting wait_for_payment (timeout)")
        return False

    def disconnect(self):
        """Disconnects from the Breez SDK."""
        logger.debug("Entering disconnect")
        try:
            # Check if the instance attribute exists and is not None
            if hasattr(self, 'instance') and self.instance:
                self.instance.disconnect()
                logger.info("Breez SDK disconnected.")
            else:
                logger.warning("Disconnect called but SDK instance was not initialized or already disconnected.")
        except Exception as e:
            logger.error(f"Error disconnecting from Breez SDK: {e}")
            # Decide if you want to re-raise or just log depending on context
            # raise # Re-raising might prevent clean shutdown

        logger.debug("Exiting disconnect")


    # --- Wallet Operations ---
    def get_info(self) -> Dict[str, Any]:
        """
        Fetches general wallet and blockchain information.

        Returns:
            Dictionary containing wallet_info and blockchain_info.
        """
        logger.debug("Entering get_info")
        try:
            self.wait_for_sync()
            info = self.instance.get_info()
            # Convert info object to dictionary for easier handling
            info_dict = {
                'wallet_info': info.wallet_info.__dict__ if info.wallet_info else None,
                'blockchain_info': info.blockchain_info.__dict__ if info.blockchain_info else None,
            }
            logger.debug(f"Fetched wallet info successfully.")
            logger.debug("Exiting get_info")
            return info_dict
        except Exception as e:
            logger.error(f"Error getting info: {e}")
            logger.debug("Exiting get_info (error)")
            raise

    def list_payments(self, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Lists payment history with optional filters.

        Args:
            params: Dictionary with optional filters (from_timestamp, to_timestamp,
                    offset, limit, filters, details). 'filters' should be a list
                    of breez_sdk_liquid.PaymentType members. 'details' should be
                    a breez_sdk_liquid.ListPaymentDetails object.
        Returns:
            List of payment dictionaries.
        Raises:
            Exception: For any SDK errors.
        """
        logger.debug(f"Entering list_payments with params: {params}")
        try:
            self.wait_for_sync()
            from_ts = int(params.get('from_timestamp')) if params and params.get('from_timestamp') is not None else None
            to_ts = int(params.get('to_timestamp')) if params and params.get('to_timestamp') is not None else None
            offset = int(params.get('offset')) if params and params.get('offset') is not None else None
            limit = int(params.get('limit')) if params and params.get('limit') is not None else None

            # --- Handle optional filters and details ---
            filters = params.get('filters') if params else None # Expects List[PaymentType]
            details_param = params.get('details') if params else None # Expects ListPaymentDetails

            # Add validation for filters/details types if needed
            if filters is not None and not isinstance(filters, list):
                 logger.warning(f"Invalid type for 'filters' parameter: {type(filters)}")
                 # Decide whether to raise error or proceed without filter
                 # raise ValueError("'filters' parameter must be a list of PaymentType")
                 filters = None # Ignore invalid input

            # Validation for details_param is trickier as it's a union type
            # We'll trust the caller passes the correct SDK object or None

            req = ListPaymentsRequest(
                from_timestamp=from_ts,
                to_timestamp=to_ts,
                offset=offset,
                limit=limit,
                filters=filters,
                details=details_param,
            )
            # --- End handle optional filters and details ---

            payments = self.instance.list_payments(req)

            # Convert payment objects to dictionaries for easier handling
            payment_list = []
            for payment in payments:
                 # Use a helper function if this conversion becomes complex/repeated
                 payment_dict = {
                    'id': getattr(payment, 'id', None), # Payments might have an ID? Check SDK docs
                    'timestamp': payment.timestamp,
                    'amount_sat': payment.amount_sat,
                    'fees_sat': payment.fees_sat,
                    'payment_type': str(payment.payment_type), # Convert Enum to string
                    'status': str(payment.status), # Convert Enum to string
                    'details': self.sdk_to_dict(payment.details) if payment.details else None, # Include details dict
                    'destination': getattr(payment, 'destination', None), # Optional field
                    'tx_id': getattr(payment, 'tx_id', None), # Optional field
                    'payment_hash': getattr(payment.details, 'payment_hash', None), # Often useful, from details
                    'swap_id': getattr(payment.details, 'swap_id', None), # Often useful, from details
                 }
                 payment_list.append(payment_dict)

            logger.debug(f"Listed {len(payment_list)} payments.")
            logger.debug("Exiting list_payments")
            return payment_list

        except Exception as e:
            logger.error(f"Error listing payments: {e}")
            logger.debug("Exiting list_payments (error)")
            raise

    def get_payment(self, identifier: str, identifier_type: str = 'payment_hash') -> Optional[Dict[str, Any]]:
        """
        Retrieves a specific payment by hash or swap ID.

        Args:
            identifier: The payment hash or swap ID string.
            identifier_type: 'payment_hash' or 'swap_id'.
        Returns:
            Payment dictionary or None if not found.
        Raises:
            ValueError: If invalid identifier_type is provided.
            Exception: For any SDK errors.
        """
        logger.debug(f"Entering get_payment with identifier: {identifier}, type: {identifier_type}")
        try:
            self.wait_for_sync()
            req = None
            if identifier_type == 'payment_hash':
                req = GetPaymentRequest.PAYMENT_HASH(identifier)
            elif identifier_type == 'swap_id':
                req = GetPaymentRequest.SWAP_ID(identifier)
            else:
                logger.warning(f"Invalid identifier_type for get_payment: {identifier_type}")
                raise ValueError("identifier_type must be 'payment_hash' or 'swap_id'")

            payment = self.instance.get_payment(req)
            if payment:
                 # Use a helper function if payment-to-dict conversion is common
                 payment_dict = {
                    'id': getattr(payment, 'id', None),
                    'timestamp': payment.timestamp,
                    'amount_sat': payment.amount_sat,
                    'fees_sat': payment.fees_sat,
                    'payment_type': str(payment.payment_type),
                    'status': str(payment.status),
                    'details': self.sdk_to_dict(payment.details) if payment.details else None,
                    'destination': getattr(payment, 'destination', None),
                    'tx_id': getattr(payment, 'tx_id', None),
                    'payment_hash': getattr(payment.details, 'payment_hash', None),
                    'swap_id': getattr(payment.details, 'swap_id', None),
                 }
                 logger.debug(f"Fetched payment: {identifier}")
                 logger.debug("Exiting get_payment (found)")
                 return payment_dict
            else:
                 logger.debug(f"Payment not found: {identifier}")
                 logger.debug("Exiting get_payment (not found)")
                 return None

        except Exception as e:
            logger.error(f"Error getting payment {identifier}: {e}")
            logger.debug("Exiting get_payment (error)")
            raise

    # --- Sending Payments ---
    def send_payment(self, destination: str, amount_sat: Optional[int] = None, amount_asset: Optional[float] = None, asset_id: Optional[str] = None, drain: bool = False) -> Dict[str, Any]:
        """
        Prepares and sends a payment to a destination (BOLT11, Liquid BIP21/address)
        for Bitcoin or other Liquid assets.

        Args:
            destination: The payment destination string.
            amount_sat: Optional amount in satoshis for Bitcoin payments.
            amount_asset: Optional amount for asset payments (as float).
            asset_id: Required if amount_asset is provided. The asset ID string.
            drain: If True, sends all funds (overrides amount arguments).
        Returns:
            Dictionary with initiated payment details.
        Raises:
            ValueError: If inconsistent or missing amount arguments.
            Exception: For any SDK errors.
        """
        logger.debug(f"Entering send_payment to {destination} (amount_sat={amount_sat}, amount_asset={amount_asset}, asset_id={asset_id}, drain={drain})")
        try:
            self.wait_for_sync()
            amount_obj = None

            if drain:
                amount_obj = PayAmount.DRAIN
                logger.debug("Sending payment using DRAIN amount.")
            elif amount_sat is not None:
                if amount_asset is not None or asset_id is not None:
                    logger.warning("Conflicting amount arguments: amount_sat provided with asset arguments.")
                    raise ValueError("Provide either amount_sat, or (amount_asset and asset_id), or drain=True.")
                amount_obj = PayAmount.BITCOIN(amount_sat)
                logger.debug(f"Sending Bitcoin payment with amount: {amount_sat} sat.")
            elif amount_asset is not None and asset_id is not None:
                 if amount_sat is not None or drain:
                     logger.warning("Conflicting amount arguments: asset arguments provided with amount_sat or drain.")
                     raise ValueError("Provide either amount_sat, or (amount_asset and asset_id), or drain=True.")
                 # False is 'is_liquid_fee' - typically false for standard asset sends
                 amount_obj = PayAmount.ASSET(asset_id, amount_asset, False)
                 logger.debug(f"Sending asset payment {asset_id} with amount: {amount_asset}.")
            else:
                 logger.warning("Missing or inconsistent amount arguments.")
                 raise ValueError("Provide either amount_sat, or (amount_asset and asset_id), or drain=True.")


            prepare_req = PrepareSendRequest(destination=destination, amount=amount_obj)
            prepare_res = self.instance.prepare_send_payment(prepare_req)

            # You might want to add a step here to check fees and potentially ask for confirmation
            logger.info(f"Prepared send payment to {destination}. Fees: {prepare_res.fees_sat} sat.")
            logger.debug(f"PrepareSendRequest response: {prepare_res.__dict__}")


            req = SendPaymentRequest(prepare_response=prepare_res)
            send_res = self.instance.send_payment(req)

            # You can track the payment status via the listener or check_payment_status later
            initiated_payment_details = {
                'status': str(send_res.payment.status), # Initial status (likely PENDING)
                'destination': getattr(send_res.payment, 'destination', None), # May or may not be present
                'fees_sat': prepare_res.fees_sat, # Prepared fees, final fees might differ slightly
                'payment_hash': getattr(send_res.payment.details, 'payment_hash', None), # Likely present for lightning
                'swap_id': getattr(send_res.payment.details, 'swap_id', None), # Likely present for onchain/liquid swaps
            }
            logger.info(f"Send payment initiated to {destination}.")
            logger.debug(f"Send payment initiated details: {initiated_payment_details}")
            logger.debug("Exiting send_payment (initiated)")

            return initiated_payment_details

        except Exception as e:
            logger.error(f"Error sending payment to {destination}: {e}")
            logger.debug("Exiting send_payment (error)")
            raise

    # --- Receiving Payments ---
    def receive_payment(self, amount: int, payment_method: str = 'LIGHTNING', description: Optional[str] = None, asset_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Prepares and generates a receive address/invoice.

        Args:
            amount: The amount to receive.
            payment_method: 'LIGHTNING', 'BITCOIN_ADDRESS', or 'LIQUID_ADDRESS'.
            description: Optional description for the payment (mainly for Lightning).
            asset_id: Optional asset ID string for receiving specific assets on Liquid.
        Returns:
            Dictionary with destination (address/invoice) and prepared fees.
        Raises:
            ValueError: If invalid payment_method is provided.
            Exception: For any SDK errors.
        """
        logger.debug(f"Entering receive_payment (amount={amount}, method={payment_method}, asset={asset_id})")
        try:
            method = getattr(PaymentMethod, payment_method.upper(), None)
            if not method:
                 logger.warning(f"Invalid payment_method: {payment_method}")
                 raise ValueError(f"Invalid payment_method: {payment_method}. Must be 'LIGHTNING', 'BITCOIN_ADDRESS', or 'LIQUID_ADDRESS'.")

            if asset_id:
                receive_amount_obj = ReceiveAmount.ASSET(asset_id, amount)
                logger.debug(f"Receiving asset {asset_id} with amount {amount}")
            else:
                receive_amount_obj = ReceiveAmount.BITCOIN(amount)
                logger.debug(f"Receiving Bitcoin with amount {amount} sat.")


            prepare_req = PrepareReceiveRequest(payment_method=method, amount=receive_amount_obj)
            prepare_res = self.instance.prepare_receive_payment(prepare_req)

            logger.info(f"Prepared receive payment ({payment_method}). Fees: {prepare_res.fees_sat} sat.")
            logger.debug(f"PrepareReceiveRequest response: {prepare_res.__dict__}")


            req = ReceivePaymentRequest(prepare_response=prepare_res, description=description)
            receive_res = self.instance.receive_payment(req)

            logger.info(f"Receive payment destination generated: {receive_res.destination}")
            logger.debug(f"Receive payment response: {receive_res.__dict__}")
            logger.debug("Exiting receive_payment")


            return {
                'destination': receive_res.destination,
                'fees_sat': prepare_res.fees_sat, # Prepared fees, final fees might differ
            }
        except Exception as e:
            logger.error(f"Error receiving payment ({payment_method}) for amount {amount}: {e}")
            logger.debug("Exiting receive_payment (error)")
            raise

    # --- Buy Bitcoin ---
    def fetch_buy_bitcoin_limits(self) -> Dict[str, Any]:
        """
        Fetches limits for buying Bitcoin (uses onchain limits).

        Returns:
            Dictionary containing receive and send limits.
        Raises:
            Exception: For any SDK errors.
        """
        logger.debug("Entering fetch_buy_bitcoin_limits")
        try:
            self.wait_for_sync()
            limits = self.instance.fetch_onchain_limits() # Onchain limits apply to Buy/Sell
            limits_dict = {
                'receive': limits.receive.__dict__ if limits.receive else None,
                'send': limits.send.__dict__ if limits.send else None,
            }
            logger.debug(f"Fetched buy/sell limits successfully.")
            logger.debug("Exiting fetch_buy_bitcoin_limits")
            return limits_dict
        except Exception as e:
            logger.error(f"Error fetching buy bitcoin limits: {e}")
            logger.debug("Exiting fetch_buy_bitcoin_limits (error)")
            raise

    def prepare_buy_bitcoin(self, provider: str, amount_sat: int) -> Dict[str, Any]:
        """
        Prepares a buy Bitcoin request.

        Args:
            provider: The buy provider string (e.g., 'MOONPAY').
            amount_sat: The amount in satoshis to buy.
        Returns:
            Dictionary with preparation details, including fees.
        Raises:
            ValueError: If invalid provider is provided.
            Exception: For any SDK errors.
        """
        logger.debug(f"Entering prepare_buy_bitcoin (provider={provider}, amount={amount_sat})")
        try:
            self.wait_for_sync()
            buy_provider = getattr(BuyBitcoinProvider, provider.upper(), None)
            if not buy_provider:
                 logger.warning(f"Invalid buy bitcoin provider: {provider}")
                 raise ValueError(f"Invalid buy bitcoin provider: {provider}.")

            req = PrepareBuyBitcoinRequest(provider=buy_provider, amount_sat=amount_sat)
            prepare_res = self.instance.prepare_buy_bitcoin(req)
            prepare_res_dict = prepare_res.__dict__
            logger.info(f"Prepared buy bitcoin with {provider}. Fees: {prepare_res.fees_sat} sat.")
            logger.debug(f"PrepareBuyBitcoinRequest response: {prepare_res_dict}")
            logger.debug("Exiting prepare_buy_bitcoin")

            return prepare_res_dict
        except Exception as e:
            logger.error(f"Error preparing buy bitcoin for {amount_sat} with {provider}: {e}")
            logger.debug("Exiting prepare_buy_bitcoin (error)")
            raise

    # Refined signature to expect the SDK object
    def buy_bitcoin(self, prepare_response: PrepareBuyBitcoinResponse) -> str:
        """
        Executes a buy Bitcoin request using prepared data.

        Args:
            prepare_response: The PrepareBuyBitcoinResponse object returned by prepare_buy_bitcoin.
        Returns:
            The URL string to complete the purchase.
        Raises:
            TypeError: If prepare_response is not the correct type.
            Exception: For any SDK errors.
        """
        logger.debug("Entering buy_bitcoin")
        try:
            self.wait_for_sync()
            # Check if it's the correct type of SDK object
            if not isinstance(prepare_response, PrepareBuyBitcoinResponse):
                 logger.error(f"buy_bitcoin expects PrepareBuyBitcoinResponse object, but received {type(prepare_response)}.")
                 raise TypeError("buy_bitcoin expects the SDK PrepareBuyBitcoinResponse object")

            req = BuyBitcoinRequest(prepare_response=prepare_response) # Pass the actual object
            url = self.instance.buy_bitcoin(req)
            logger.info(f"Buy bitcoin URL generated.")
            logger.debug("Exiting buy_bitcoin")
            return url
        except Exception as e:
            logger.error(f"Error executing buy bitcoin: {e}")
            logger.debug("Exiting buy_bitcoin (error)")
            raise

    # --- Fiat Currencies ---
    def list_fiat_currencies(self) -> List[Dict[str, Any]]:
        """
        Lists supported fiat currencies.

        Returns:
            List of fiat currency dictionaries.
        """
        logger.debug("Entering list_fiat_currencies")
        try:
            self.wait_for_sync() # Fiat data might need sync
            currencies = self.instance.list_fiat_currencies()
            currencies_list = [c.__dict__ for c in currencies]
            logger.debug(f"Listed {len(currencies_list)} fiat currencies.")
            logger.debug("Exiting list_fiat_currencies")
            return currencies_list
        except Exception as e:
            logger.error(f"Error listing fiat currencies: {e}")
            logger.debug("Exiting list_fiat_currencies (error)")
            raise

    def fetch_fiat_rates(self) -> List[Dict[str, Any]]:
        """
        Fetches current fiat exchange rates.

        Returns:
            List of fiat rate dictionaries.
        """
        logger.debug("Entering fetch_fiat_rates")
        try:
            self.wait_for_sync() # Fiat data might need sync
            rates = self.instance.fetch_fiat_rates()
            rates_list = [r.__dict__ for r in rates]
            logger.debug(f"Fetched {len(rates_list)} fiat rates.")
            logger.debug("Exiting fetch_fiat_rates")
            return rates_list
        except Exception as e:
            logger.error(f"Error fetching fiat rates: {e}")
            logger.debug("Exiting fetch_fiat_rates (error)")
            raise

    # --- LNURL Operations ---
    def parse_input(self, input_str: str) -> Dict[str, Any]:
        """
        Parses various input types (LNURL, addresses, invoices, etc.).

        Args:
            input_str: The string input to parse.
        Returns:
            Dictionary representing the parsed input details.
        Raises:
            Exception: For any SDK errors during parsing.
        """
        logger.debug(f"Entering parse_input with input: {input_str}")
        try:
            self.wait_for_sync() # Parsing might require network interaction
            parsed_input = self.instance.parse(input_str)
            # Convert the specific InputType object to a dictionary
            # Access .data on the *instance* of the parsed input, not the type
            if isinstance(parsed_input, InputType.BITCOIN_ADDRESS):
                 result = {'type': 'BITCOIN_ADDRESS', 'address': parsed_input.address.address}
            elif isinstance(parsed_input, InputType.BOLT11):
                 result = {'type': 'BOLT11', 'invoice': parsed_input.invoice.__dict__}
            elif isinstance(parsed_input, InputType.LN_URL_PAY):
                 # Access data on the instance: parsed_input.data
                 result = {'type': 'LN_URL_PAY', 'data': parsed_input.data.__dict__}
            elif isinstance(parsed_input, InputType.LN_URL_AUTH):
                 # Access data on the instance: parsed_input.data
                 result = {'type': 'LN_URL_AUTH', 'data': parsed_input.data.__dict__}
            elif isinstance(parsed_input, InputType.LN_URL_WITHDRAW):
                 # Access data on the instance: parsed_input.data
                 result = {'type': 'LN_URL_WITHDRAW', 'data': parsed_input.data.__dict__}
            elif isinstance(parsed_input, InputType.LIQUID_ADDRESS):
                 result = {'type': 'LIQUID_ADDRESS', 'address': parsed_input.address.address}
            elif isinstance(parsed_input, InputType.BIP21):
                 result = {'type': 'BIP21', 'data': parsed_input.bip21.__dict__}
            elif isinstance(parsed_input, InputType.NODE_ID):
                 result = {'type': 'NODE_ID', 'node_id': parsed_input.node_id}
            else:
                 # Log raw data for unhandled types to aid debugging
                 logger.warning(f"Parsed unknown input type: {type(parsed_input)}")
                 result = {'type': 'UNKNOWN', 'raw_input': input_str, 'raw_parsed_object': str(parsed_input)}

            logger.debug(f"Parsed input successfully. Type: {result.get('type')}")
            logger.debug("Exiting parse_input")

            return result
        except Exception as e:
            logger.error(f"Error parsing input '{input_str}': {e}")
            logger.debug("Exiting parse_input (error)")
            raise

    # Corrected type hint to LnUrlPayRequestData
    def prepare_lnurl_pay(self, data: LnUrlPayRequestData, amount_sat: int, comment: Optional[str] = None, validate_success_action_url: bool = True) -> Dict[str, Any]:
        """
        Prepares an LNURL-Pay request.

        Args:
            data: The LnUrlPayRequestData object from a parsed LNURL_PAY input's .data attribute.
            amount_sat: Amount in satoshis.
            comment: Optional comment.
            validate_success_action_url: Whether to validate the success action URL.
        Returns:
            Dictionary with preparation details.
        Raises:
            TypeError: If data is not the correct object type.
            Exception: For any SDK errors.
        """
        logger.debug(f"Entering prepare_lnurl_pay (amount={amount_sat}, comment={comment})")
        try:
            self.wait_for_sync()
            # Check if it's the correct type of SDK object
            if not isinstance(data, LnUrlPayRequestData):
                 logger.error(f"prepare_lnurl_pay expects LnUrlPayRequestData object, but received {type(data)}.")
                 raise TypeError("prepare_lnurl_pay expects the SDK LnUrlPayRequestData object")


            # Handle amount format for PayAmount
            pay_amount = PayAmount.BITCOIN(amount_sat)

            req = PrepareLnUrlPayRequest(
                 data=data, # Use the passed object
                 amount=pay_amount,
                 comment=comment,
                 validate_success_action_url=validate_success_action_url,
                 bip353_address=getattr(data, 'bip353_address', None) # Get bip353_address from the object
            )
            prepare_res = self.instance.prepare_lnurl_pay(req)
            prepare_res_dict = prepare_res.__dict__
            logger.info(f"Prepared LNURL-Pay. Fees: {prepare_res.fees_sat} sat.")
            logger.debug(f"PrepareLnUrlPayRequest response: {prepare_res_dict}")
            logger.debug("Exiting prepare_lnurl_pay")

            return prepare_res_dict
        except Exception as e:
            logger.error(f"Error preparing LNURL-Pay: {e}")
            logger.debug("Exiting prepare_lnurl_pay (error)")
            raise

    # Refined signature to expect the SDK object
    def lnurl_pay(self, prepare_response: PrepareLnUrlPayResponse) -> Optional[Dict[str, Any]]:
        """
        Executes an LNURL-Pay payment using prepared data.

        Args:
            prepare_response: The PrepareLnUrlPayResponse object returned by prepare_lnurl_pay.
        Returns:
            Dictionary with payment result details, or None if no specific result.
        Raises:
            TypeError: If prepare_response is not the correct type.
            Exception: For any SDK errors.
        """
        logger.debug("Entering lnurl_pay")
        try:
            self.wait_for_sync()
            # Check if it's the correct type of SDK object
            if not isinstance(prepare_response, PrepareLnUrlPayResponse):
                 logger.error(f"lnurl_pay expects PrepareLnUrlPayResponse object, but received {type(prepare_response)}.")
                 raise TypeError("lnurl_pay expects the SDK PrepareLnUrlPayResponse object")

            req = LnUrlPayRequest(prepare_response=prepare_response) # Pass the actual object
            result = self.instance.lnurl_pay(req)
            result_dict = result.__dict__ if result else None # Result type depends on success action
            logger.info("Executed LNURL-Pay.")
            logger.debug(f"LNURL-Pay result: {result_dict}")
            logger.debug("Exiting lnurl_pay")
            return result_dict
        except Exception as e:
            logger.error(f"Error executing LNURL-Pay: {e}")
            logger.debug("Exiting lnurl_pay (error)")
            raise

    # Corrected type hint to LnUrlAuthRequestData
    def lnurl_auth(self, data: LnUrlAuthRequestData) -> bool:
        """
        Performs LNURL-Auth.

        Args:
            data: The LnUrlAuthRequestData object from a parsed LNURL_AUTH input's .data attribute.
        Returns:
            True if authentication was successful, False otherwise.
        Raises:
            TypeError: If data is not the correct object type.
            Exception: For any SDK errors.
        """
        logger.debug("Entering lnurl_auth")
        try:
            self.wait_for_sync()
             # Check if it's the correct type of SDK object
            if not isinstance(data, LnUrlAuthRequestData):
                 logger.error(f"lnurl_auth expects LnUrlAuthRequestData object, but received {type(data)}.")
                 raise TypeError("lnurl_auth expects the SDK LnUrlAuthRequestData object")

            result = self.instance.lnurl_auth(data) # Pass the actual object
            is_ok = result.is_ok()
            if is_ok:
                 logger.info("LNURL-Auth successful.")
            else:
                 # Log the error message from the result if available
                 error_msg = getattr(result, 'error', 'Unknown error')
                 logger.warning(f"LNURL-Auth failed. Error: {error_msg}")
            logger.debug(f"LNURL-Auth result: {is_ok}")
            logger.debug("Exiting lnurl_auth")
            return is_ok
        except Exception as e:
            logger.error(f"Error performing LNURL-Auth: {e}")
            logger.debug("Exiting lnurl_auth (error)")
            raise

    # Corrected type hint to LnurlWithdrawRequestData
    def lnurl_withdraw(self, data: LnUrlWithdrawRequestData, amount_msat: int, comment: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Performs LNURL-Withdraw.

        Args:
            data: The LnUrlWithdrawRequestData object from a parsed LNURL_WITHDRAW input's .data attribute.
            amount_msat: Amount in millisatoshis to withdraw.
            comment: Optional comment string.
        Returns:
            Dictionary with withdrawal result details, or None if no specific result.
        Raises:
            TypeError: If data is not the correct object type.
            Exception: For any SDK errors.
        """
        logger.debug(f"Entering lnurl_withdraw (amount_msat={amount_msat}, comment={comment})")
        try:
            self.wait_for_sync()
            # Check if it's the correct type of SDK object
            if not isinstance(data, LnUrlWithdrawRequestData):
                 logger.error(f"lnurl_withdraw expects LnUrlWithdrawRequestData object, but received {type(data)}.")
                 raise TypeError("lnurl_withdraw expects the SDK LnUrlWithdrawRequestData object")

            # Basic validation for amount and comment
            if not isinstance(amount_msat, int) or amount_msat <= 0:
                 logger.warning(f"Invalid amount_msat provided: {amount_msat}")
                 raise ValueError("amount_msat must be a positive integer.")
            if comment is not None and not isinstance(comment, str):
                 logger.warning(f"Invalid comment type provided: {type(comment)}")
                 raise ValueError("comment must be a string or None.")

            result = self.instance.lnurl_withdraw(data, amount_msat, comment) # Pass the actual object
            result_dict = result.__dict__ if result else None # Check result type
            logger.info("Executed LNURL-Withdraw.")
            logger.debug(f"LNURL-Withdraw result: {result_dict}")
            logger.debug("Exiting lnurl_withdraw")
            return result_dict
        except Exception as e:
            logger.error(f"Error executing LNURL-Withdraw: {e}")
            logger.debug("Exiting lnurl_withdraw (error)")
            raise

    # --- Onchain Operations ---
    # fetch_pay_onchain_limits is covered by fetch_onchain_limits (public method)

    def prepare_pay_onchain(self, amount_sat: Optional[int] = None, drain: bool = False, fee_rate_sat_per_vbyte: Optional[int] = None) -> Dict[str, Any]:
        """
        Prepares an onchain payment (Bitcoin address).

        Args:
            amount_sat: Optional amount in satoshis (required unless drain is True).
            drain: If True, prepares to send all funds.
            fee_rate_sat_per_vbyte: Optional custom fee rate.
        Returns:
            Dictionary with preparation details.
        Raises:
            ValueError: If amount is missing for non-drain payment.
            Exception: For any SDK errors.
        """
        logger.debug(f"Entering prepare_pay_onchain (amount={amount_sat}, drain={drain}, fee_rate={fee_rate_sat_per_vbyte})")
        try:
            # Determine amount object based on inputs
            if drain:
                amount_obj = PayAmount.DRAIN
                logger.debug("Preparing onchain payment using DRAIN amount.")
            elif amount_sat is not None:
                amount_obj = PayAmount.BITCOIN(amount_sat)
                logger.debug(f"Preparing onchain payment with amount: {amount_sat} sat.")
            else:
                 logger.warning("Amount is missing for non-drain pay onchain.")
                 raise ValueError("Amount must be provided for non-drain payments.")

            # Optional fee rate validation
            if fee_rate_sat_per_vbyte is not None and (not isinstance(fee_rate_sat_per_vbyte, int) or fee_rate_sat_per_vbyte <= 0):
                 logger.warning(f"Invalid fee_rate_sat_per_vbyte provided: {fee_rate_sat_per_vbyte}")
                 raise ValueError("fee_rate_sat_per_vbyte must be a positive integer or None.")


            req = PreparePayOnchainRequest(amount=amount_obj, fee_rate_sat_per_vbyte=fee_rate_sat_per_vbyte)
            prepare_res = self.instance.prepare_pay_onchain(req)
            prepare_res_dict = prepare_res.__dict__
            logger.info(f"Prepared pay onchain. Total fees: {prepare_res.total_fees_sat} sat.")
            logger.debug(f"PreparePayOnchainRequest response: {prepare_res_dict}")
            logger.debug("Exiting prepare_pay_onchain")
            return prepare_res_dict
        except Exception as e:
            logger.error(f"Error preparing pay onchain: {e}")
            logger.debug("Exiting prepare_pay_onchain (error)")
            raise

    # Refined signature to expect the SDK object
    def pay_onchain(self, address: str, prepare_response: PreparePayOnchainResponse):
        """
        Executes an onchain payment using prepared data.

        Args:
            address: The destination Bitcoin address string.
            prepare_response: The PreparePayOnchainResponse object returned by prepare_pay_onchain.
        Raises:
            TypeError: If prepare_response is not the correct type.
            ValueError: If address is invalid.
            Exception: For any SDK errors.
        """
        logger.debug(f"Entering pay_onchain to {address}")
        try:
            self.wait_for_sync()
             # Check if it's the correct type of SDK object
            if not isinstance(prepare_response, PreparePayOnchainResponse):
                 logger.error(f"pay_onchain expects PreparePayOnchainResponse object, but received {type(prepare_response)}.")
                 raise TypeError("pay_onchain expects the SDK PreparePayOnchainResponse object")

            # Basic check for address format (could add more robust validation)
            if not isinstance(address, str) or not address:
                 logger.warning("Invalid or empty destination address provided for pay_onchain.")
                 raise ValueError("Destination address must be a non-empty string.")


            req = PayOnchainRequest(address=address, prepare_response=prepare_response) # Pass the actual object
            self.instance.pay_onchain(req)
            logger.info(f"Onchain payment initiated to {address}.")
            logger.debug("Exiting pay_onchain")

            # Note: Onchain payments might not trigger an immediate SDK event like lightning payments
            # You might need to poll list_payments or rely on webhooks to track final status.

        except Exception as e:
            logger.error(f"Error executing pay onchain to {address}: {e}")
            logger.debug("Exiting pay_onchain (error)")
            raise

    # list_refundable_payments method (already present, returns list of RefundableSwap objects)
    def list_refundable_payments(self) -> List[RefundableSwap]:
         """
         Lists refundable onchain swaps.

         Returns:
             List of RefundableSwap objects.
         Raises:
             Exception: For any SDK errors.
         """
         logger.debug("Entering list_refundable_payments")
         try:
             self.wait_for_sync()  # Ensure sync before executing
             refundable_payments = self.instance.list_refundables()
             logger.debug(f"Found {len(refundable_payments)} refundable payments.")
             logger.debug("Exiting list_refundable_payments")
             return refundable_payments # Return the list of objects directly

         except Exception as e:
             logger.error(f"Error listing refundable payments: {e}")
             logger.debug("Exiting list_refundable_payments (error)")
             raise

    # Updated signature and type hint to RefundableSwap and explicit refund_address
    def execute_refund(self, refundable_swap: RefundableSwap, refund_address: str, fee_rate_sat_per_vbyte: int):
        """
        Executes a refund for a refundable swap.

        Args:
            refundable_swap: The RefundableSwap object to refund.
            refund_address: The destination address string for the refund.
            fee_rate_sat_per_vbyte: The desired fee rate in satoshis per vbyte for the refund transaction.
        Raises:
            TypeError: If refundable_swap is not the correct type.
            ValueError: If refund_address or fee_rate_sat_per_vbyte is invalid.
            Exception: For any SDK errors.
        """
        # Using getattr with a default for logging in case refundable_swap is None or malformed (though type hint should prevent this)
        logger.debug(f"Entering execute_refund for swap {getattr(refundable_swap, 'swap_address', 'N/A')} to {refund_address} with fee rate {fee_rate_sat_per_vbyte}")
        try:
            self.wait_for_sync()
            # Check if it's the correct type of SDK object
            if not isinstance(refundable_swap, RefundableSwap):
                 logger.error(f"execute_refund expects RefundableSwap object, but received {type(refundable_swap)}.")
                 raise TypeError("execute_refund expects the SDK RefundableSwap object")

            # Basic check for refund_address format (could add more robust validation)
            if not isinstance(refund_address, str) or not refund_address:
                 logger.warning("Invalid or empty refund_address provided for execute_refund.")
                 raise ValueError("Refund destination address must be a non-empty string.")

            if not isinstance(fee_rate_sat_per_vbyte, int) or fee_rate_sat_per_vbyte <= 0:
                 logger.warning(f"Invalid fee_rate_sat_per_vbyte provided: {fee_rate_sat_per_vbyte}")
                 raise ValueError("fee_rate_sat_per_vbyte must be a positive integer.")


            req = RefundRequest(
                swap_address=refundable_swap.swap_address, # Use address from the object
                refund_address=refund_address,
                fee_rate_sat_per_vbyte=fee_rate_sat_per_vbyte
            )
            self.instance.refund(req)
            logger.info(f"Refund initiated for swap {refundable_swap.swap_address} to {refund_address}.")
            logger.debug("Exiting execute_refund")

            # Note: Onchain refunds might not trigger an immediate SDK event
            # You might need to poll list_payments or rely on webhooks to track final status.


        except Exception as e:
            logger.error(f"Error executing refund for swap {getattr(refundable_swap, 'swap_address', 'N/A')}: {e}")
            logger.debug("Exiting execute_refund (error)")
            raise

    # rescan_swaps method (already present)
    def rescan_swaps(self):
         """
         Rescans onchain swaps.

         Raises:
             Exception: For any SDK errors.
         """
         logger.debug("Entering rescan_swaps")
         try:
             self.wait_for_sync() # Ensure sync before executing
             self.instance.rescan_onchain_swaps()
             logger.info("Onchain swaps rescan initiated.")
             logger.debug("Exiting rescan_swaps")

         except Exception as e:
             logger.error(f"Error rescanning swaps: {e}")
             logger.debug("Exiting rescan_swaps (error)")
             raise

    def recommended_fees(self) -> Dict[str, int]:
        """
        Fetches recommended transaction fees.

        Returns:
            Dictionary with fee rate estimates (e.g., {'fastest': 100, 'half_hour': 50, ...}).
        Raises:
            Exception: For any SDK errors.
        """
        logger.debug("Entering recommended_fees")
        try:
            self.wait_for_sync() # Fee estimates might need network
            fees = self.instance.recommended_fees()
            # Assuming recommended_fees returns an object with __dict__ or similar fee structure
            fees_dict = fees.__dict__ if fees else {} # Convert to dict
            logger.debug(f"Fetched recommended fees: {fees_dict}")
            logger.debug("Exiting recommended_fees")
            return fees_dict
        except Exception as e:
            logger.error(f"Error fetching recommended fees: {e}")
            logger.debug("Exiting recommended_fees (error)")
            raise

    def handle_payments_waiting_fee_acceptance(self):
        """
        Fetches and automatically accepts payments waiting for fee acceptance.
        In a real app, you would add logic to decide whether to accept the fees.

        Raises:
             Exception: For any SDK errors.
        """
        logger.debug("Entering handle_payments_waiting_fee_acceptance")
        try:
            self.wait_for_sync()
            logger.info("Checking for payments waiting for fee acceptance...")
            # Filter for WAITING_FEE_ACCEPTANCE state
            payments_waiting = self.instance.list_payments(
                ListPaymentsRequest(states=[PaymentState.WAITING_FEE_ACCEPTANCE])
            )

            handled_count = 0
            for payment in payments_waiting:
                # Double-check payment type and swap_id as per doc example
                if not isinstance(payment.details, PaymentDetails.BITCOIN) or not payment.details.swap_id:
                    logger.warning(f"Skipping payment in WAITING_FEE_ACCEPTANCE state without Bitcoin details or swap_id: {getattr(payment, 'destination', 'N/A')}")
                    continue

                swap_id = payment.details.swap_id
                logger.info(f"Found payment waiting fee acceptance: {getattr(payment, 'destination', 'N/A')} (Swap ID: {swap_id})")

                fetch_fees_req = FetchPaymentProposedFeesRequest(swap_id=swap_id)
                fetch_fees_response = self.instance.fetch_payment_proposed_fees(fetch_fees_req)

                logger.info(
                    f"Payer sent {fetch_fees_response.payer_amount_sat} "
                    f"and currently proposed fees are {fetch_fees_response.fees_sat}"
                )

                # --- Decision Point: Accept Fees? ---
                # In a real application, you would implement logic here to decide if the proposed fees
                # are acceptable based on your application's criteria.
                # For this example, we will automatically accept.
                logger.info(f"Automatically accepting proposed fees for swap {swap_id}.")
                # --- End Decision Point ---

                accept_fees_req = AcceptPaymentProposedFeesRequest(response=fetch_fees_response)
                self.instance.accept_payment_proposed_fees(accept_fees_req)
                logger.info(f"Accepted proposed fees for swap {swap_id}.")
                handled_count += 1

            logger.info(f"Finished checking for payments waiting fee acceptance. Handled {handled_count}.")
            logger.debug("Exiting handle_payments_waiting_fee_acceptance")

        except Exception as e:
            logger.error(f"Error handling payments waiting fee acceptance: {e}")
            logger.debug("Exiting handle_payments_waiting_fee_acceptance (error)")
            raise


    # --- Working with Non-Bitcoin Assets ---
    # Asset Metadata configuration is done in __init__

    # prepare_receive_asset is covered by receive_payment with asset_id parameter

    # prepare_send_payment_asset is covered by the updated send_payment with asset_id parameter

    def fetch_asset_balance(self) -> Dict[str, Any]:
        """
        Fetches the balance of all assets (Bitcoin and others).
        Note: This information is part of get_info().

        Returns:
            Dictionary containing asset balances.
        Raises:
            Exception: For any SDK errors from get_info.
        """
        logger.debug("Entering fetch_asset_balance")
        try:
            # This information is part of get_info().wallet_info.asset_balances
            # Calling get_info handles sync and error logging
            info = self.get_info()
            # Extract asset_balances from the returned info dictionary
            asset_balances = info.get('wallet_info', {}).get('asset_balances', {})

            # The asset_balances value is a list of AssetBalance objects.
            # You might want to convert these to dictionaries too for consistency if needed.
            # For now, returning the list of objects as is fetched by get_info.
            # If conversion is needed:
            # converted_balances = [bal.__dict__ for bal in asset_balances]

            logger.debug(f"Fetched asset balances: {asset_balances}")
            logger.debug("Exiting fetch_asset_balance")
            return asset_balances # Or return converted_balances

        except Exception as e:
             # get_info already logs, this catch is mainly to ensure debug exit logging
             # If get_info fails, it raises, so this block might not be reached
             logger.error(f"Error fetching asset balance (via get_info): {e}")
             logger.debug("Exiting fetch_asset_balance (error)")
             raise


    # --- Webhook Management ---
    def register_webhook(self, webhook_url: str):
        """
        Registers a webhook URL for receiving notifications.

        Args:
            webhook_url: The URL string to register.
        Raises:
            ValueError: If webhook_url is invalid.
            Exception: For any SDK errors.
        """
        logger.debug(f"Entering register_webhook with URL: {webhook_url}")
        try:
            self.wait_for_sync() # Might require network
            # Basic URL format validation (can be made more robust)
            if not isinstance(webhook_url, str) or not webhook_url.startswith('https://'):
                 logger.warning(f"Invalid webhook_url provided: {webhook_url}")
                 raise ValueError("Webhook URL must be a valid HTTPS URL.")

            self.instance.register_webhook(webhook_url)
            logger.info(f"Webhook registered: {webhook_url}")
            logger.debug("Exiting register_webhook")
        except Exception as e:
            logger.error(f"Error registering webhook {webhook_url}: {e}")
            logger.debug("Exiting register_webhook (error)")
            raise

    def unregister_webhook(self):
        """
        Unregisters the currently registered webhook.

        Raises:
            Exception: For any SDK errors.
        """
        logger.debug("Entering unregister_webhook")
        try:
            self.wait_for_sync() # Might require network
            self.instance.unregister_webhook()
            logger.info("Webhook unregistered.")
            logger.debug("Exiting unregister_webhook")
        except Exception as e:
            logger.error(f"Error unregistering webhook: {e}")
            logger.debug("Exiting unregister_webhook (error)")
            raise

    # --- Utilities and Message Signing ---
    # parse_input is implemented above

    def sign_message(self, message: str) -> Dict[str, str]:
        """
        Signs a message with the wallet's key.

        Args:
            message: The message string to sign.
        Returns:
            Dictionary with the signature and the wallet's public key string.
        Raises:
            ValueError: If message is invalid.
            Exception: For any SDK errors.
        """
        # Log truncated message to avoid logging potentially sensitive full messages
        logger.debug(f"Entering sign_message with message (truncated): {message[:50]}...")
        try:
            self.wait_for_sync()
            if not isinstance(message, str) or not message:
                 logger.warning("Invalid or empty message provided for signing.")
                 raise ValueError("Message to sign must be a non-empty string.")

            req = SignMessageRequest(message=message)
            sign_res = self.instance.sign_message(req)
            # Fetch info AFTER signing to get the pubkey that was used
            info = self.instance.get_info()

            pubkey = info.wallet_info.pubkey if info and info.wallet_info else None

            if not pubkey:
                 logger.warning("Could not retrieve wallet pubkey after signing message.")
                 # Decide how to handle this - return None for pubkey or raise error
                 # Returning None for pubkey might be acceptable, the signature is the main result.
                 pass


            result = {
                 'signature': sign_res.signature,
                 'pubkey': pubkey,
            }
            logger.info("Message signed.")
            logger.debug("Exiting sign_message")
            return result
        except Exception as e:
            logger.error(f"Error signing message: {e}")
            logger.debug("Exiting sign_message (error)")
            raise

    def check_message(self, message: str, pubkey: str, signature: str) -> bool:
        """
        Verifies a signature against a message and public key.

        Args:
            message: The original message string.
            pubkey: The public key string used for signing.
            signature: The signature string to verify.
        Returns:
            True if the signature is valid, False otherwise.
        Raises:
            ValueError: If message, pubkey, or signature are invalid.
            Exception: For any SDK errors.
        """
        logger.debug(f"Entering check_message for message (truncated): {message[:50]}...")
        try:
            self.wait_for_sync() # Might require network to verify
            if not isinstance(message, str) or not message:
                 logger.warning("Invalid or empty message provided for checking.")
                 raise ValueError("Message to check must be a non-empty string.")
            if not isinstance(pubkey, str) or not pubkey:
                 logger.warning("Invalid or empty pubkey provided for checking.")
                 raise ValueError("Pubkey must be a non-empty string.")
            if not isinstance(signature, str) or not signature:
                 logger.warning("Invalid or empty signature provided for checking.")
                 raise ValueError("Signature must be a non-empty string.")


            req = CheckMessageRequest(message=message, pubkey=pubkey, signature=signature)
            check_res = self.instance.check_message(req)
            is_valid = check_res.is_valid
            logger.info(f"Message signature check result: {is_valid}")
            logger.debug("Exiting check_message")
            return is_valid
        except Exception as e:
            logger.error(f"Error checking message signature: {e}")
            logger.debug("Exiting check_message (error)")
            raise

    # External Input Parser configuration is done in __init__

    # Payment Limits
    # Keeping the explicit fetch methods as they are clearer

    def fetch_lightning_limits(self) -> Dict[str, Any]:
        """
        Fetches current Lightning payment limits.

        Returns:
            Dictionary containing receive and send limits.
        Raises:
             Exception: For any SDK errors.
        """
        logger.debug("Entering fetch_lightning_limits")
        try:
            self.wait_for_sync()
            limits = self.instance.fetch_lightning_limits()
            limits_dict = {
                'receive': limits.receive.__dict__ if limits.receive else None,
                'send': limits.send.__dict__ if limits.send else None,
            }
            logger.debug(f"Fetched lightning limits: {limits_dict}")
            logger.debug("Exiting fetch_lightning_limits")
            return limits_dict
        except Exception as e:
            logger.error(f"Error fetching lightning limits: {e}")
            logger.debug("Exiting fetch_lightning_limits (error)")
            raise

    def fetch_onchain_limits(self) -> Dict[str, Any]:
        """
        Fetches current onchain payment limits (used for Bitcoin send/receive).

        Returns:
            Dictionary containing receive and send limits.
        Raises:
             Exception: For any SDK errors.
        """
        logger.debug("Entering fetch_onchain_limits")
        try:
            self.wait_for_sync()
            limits = self.instance.fetch_onchain_limits()
            limits_dict = {
                'receive': limits.receive.__dict__ if limits.receive else None,
                'send': limits.send.__dict__ if limits.send else None,
            }
            logger.debug(f"Fetched onchain limits: {limits_dict}")
            logger.debug("Exiting fetch_onchain_limits")
            return limits_dict
        except Exception as e:
            logger.error(f"Error fetching onchain limits: {e}")
            logger.debug("Exiting fetch_onchain_limits (error)")
            raise

    def sdk_to_dict(self, obj):
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        if isinstance(obj, list):
            return [self.sdk_to_dict(i) for i in obj]
        if hasattr(obj, '__dict__'):
            return {k: self.sdk_to_dict(v) for k, v in obj.__dict__.items()}
        return str(obj)  # fallback