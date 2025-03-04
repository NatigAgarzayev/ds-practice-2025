import sys
import os
import grpc
import json
import threading
import uuid  
from flask import Flask, request
from flask_cors import CORS


# Ensure utils/pb is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))

# import fraud_detection_pb2 as fraud_detection
# import fraud_detection_pb2_grpc as fraud_detection_grpc
from fraud_detection import fraud_detection_pb2 as fraud_detection
from fraud_detection import fraud_detection_pb2_grpc as fraud_detection_grpc

# import transaction_verification_pb2 as transaction_verification
# import transaction_verification_pb2_grpc as transaction_verification_grpc
from transaction_verification.transaction_verification_pb2 import TransactionVerificationRequest, Item
from transaction_verification import transaction_verification_pb2_grpc as transaction_verification_grpc


# import suggestions_pb2 as suggestions
# import suggestions_pb2_grpc as suggestions_grpc
from suggestions import suggestions_pb2 as suggestions
from suggestions import suggestions_pb2_grpc as suggestions_grpc
import logging

# Configure logging
logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    level=logging.INFO  # Change to DEBUG for more details
)

logger = logging.getLogger(__name__)


app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

def check_fraud(order_id, amount, result):
    logger.info(f"Checking fraud for Order ID: {order_id} with Amount: {amount}")
    
    with grpc.insecure_channel('fraud_detection:50051') as channel:
        stub = fraud_detection_grpc.FraudDetectionStub(channel)
        response = stub.CheckFraud(fraud_detection.FraudCheckRequest(order_id=order_id, amount=amount))

    result['fraud'] = response.is_fraudulent
    logger.info(f"Fraud check result for Order ID: {order_id}: {'Fraud Detected' if response.is_fraudulent else 'Legitimate Transaction'}")


def verify_transaction(request_data, result, order_id):
    """Converts JSON payload to Protobuf and calls the gRPC service."""
    user_id = request_data.get("user", {}).get("name") or request_data.get("userId") or "unknown"
    credit_card = request_data.get("creditCard", {}).get("number", "")
    
    logger.info(f"Verifying transaction for Order ID: {order_id}, User ID: {user_id}")

    protobuf_items = [
        Item(book_id=item["name"], quantity=item["quantity"])
        for item in request_data.get("items", [])
        if isinstance(item, dict) and "name" in item and "quantity" in item
    ]

    request = TransactionVerificationRequest(
        transaction_id=order_id,
        user_id=user_id,
        items=protobuf_items,
        credit_card=credit_card
    )

    logger.debug(f"Transaction Request: {request}")

    with grpc.insecure_channel('transaction_verification:50052') as channel:
        stub = transaction_verification_grpc.TransactionVerificationStub(channel)
        response = stub.VerifyTransaction(request)

    result['valid_transaction'] = response.is_valid
    logger.info(f"Transaction verification result for Order ID: {order_id}: {'Valid' if response.is_valid else 'Invalid'} - {response.message}")



def get_suggestions(user_id, num_suggestions):
    """Calls the book suggestions gRPC service and returns the response."""
    logger.info(f"Fetching {num_suggestions} book suggestions for User ID: {user_id}")

    with grpc.insecure_channel('suggestions:50053') as channel:
        stub = suggestions_grpc.SuggestionsStub(channel)
        request = suggestions.SuggestionsRequest(user_id=user_id, num_suggestions=num_suggestions)
        response = stub.GetBookSuggestions(request)

    suggested_books = [{"title": book} for book in response.books]
    
    logger.info(f"Suggested Books for User ID {user_id}: {suggested_books}")
    return suggested_books


@app.route('/checkout', methods=['POST'])
def checkout():
    """Handles the checkout process by calling all gRPC services."""
    request_data = json.loads(request.data)
    order_id = request_data.get("orderId") or request_data.get("order_id") or str(uuid.uuid4())
    user_id = request_data.get("userId") or request_data.get("user_id") or "unknown"
    amount = request_data.get("amount", 0)

    logger.info(f"Received checkout request for Order ID: {order_id}, User ID: {user_id}, Amount: {amount}")

    result = {}
    threads = []

    # Start fraud check and transaction verification
    threads.append(threading.Thread(target=check_fraud, args=(order_id, amount, result)))
    threads.append(threading.Thread(target=verify_transaction, args=(request_data, result, order_id)))

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    logger.debug(f"DEBUG RESULT BEFORE SUGGESTIONS: {result}")

    # Determine order status
    if result.get('valid_transaction', False):
        if result.get('fraud', False):
            status = "Order Approved"

            # ✅ Fetch book suggestions **only if the order is approved**
            suggested_books = get_suggestions(user_id, 10)
            result['suggested_books'] = suggested_books
        else:
            status = "Order Pending Review (Fraud Detected)"
    else:
        status = "Order Rejected"

    response = {
        'orderId': order_id,
        'status': status,
        'suggestedBooks': result.get('suggested_books', [])
    }

    logger.info(f"Checkout completed for Order ID: {order_id}, Status: {status}")
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0')
