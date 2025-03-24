import sys
import os
import grpc
import json
import threading
import uuid
import time
from flask import Flask, request
from flask_cors import CORS

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils")))

from fraud_detection import fraud_detection_pb2 as fraud_detection
from fraud_detection import fraud_detection_pb2_grpc as fraud_detection_grpc    
from transaction_verification import transaction_verification_pb2 as txn
from transaction_verification import transaction_verification_pb2_grpc as txn_grpc
from suggestions import suggestions_pb2 as suggestions
from suggestions import suggestions_pb2_grpc as suggestions_grpc
from vector_clock import VectorClock

import logging
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

SERVICES = ["orchestrator", "transaction_verification", "fraud_detection"]

# In-memory cache to store order vector clocks
order_clocks = {}

def init_services(order_id, request_data):
    clock = VectorClock(SERVICES)
    clock.increment("orchestrator")
    order_clocks[order_id] = clock

    logger.info(f"[{order_id}] Initializing all backend services")

    def cache_txn_verification():
        with grpc.insecure_channel("transaction_verification:50052") as channel:
            stub = txn_grpc.TransactionVerificationStub(channel)
            request = txn.CachedOrderRequest(order_id=order_id, payload=json.dumps(request_data), clock=json.dumps(clock.to_dict()))
            stub.CacheOrder(request)

    def cache_fraud_detection():
        with grpc.insecure_channel("fraud_detection:50051") as channel:
            stub = fraud_detection_grpc.FraudDetectionStub(channel)
            request = fraud_detection.CachedOrderRequest(order_id=order_id, payload=json.dumps(request_data), clock=json.dumps(clock.to_dict()))
            stub.CacheOrder(request)

    t1 = threading.Thread(target=cache_txn_verification)
    t2 = threading.Thread(target=cache_fraud_detection)
    t1.start(); t2.start(); t1.join(); t2.join()

@app.route('/checkout', methods=['POST'])
def checkout():
    data = request.get_json()
    order_id = str(uuid.uuid4())
    user_id = data.get("user", {}).get("name", "guest")
    logger.info(f"[{order_id}] Checkout request from user: {user_id}")

    init_services(order_id, data)

    # Trigger verification first
    logger.info(f"[{order_id}] Triggering Transaction Verification")
    with grpc.insecure_channel("transaction_verification:50052") as channel:
        stub = txn_grpc.TransactionVerificationStub(channel)
        verify_resp = stub.ProcessOrder(txn.OrderProcessRequest(order_id=order_id))

    if not verify_resp.is_valid:
        return {
            "orderId": order_id,
            "status": "Order Rejected",
            "suggestedBooks": []
        }

    # Trigger fraud detection only if valid
    logger.info(f"[{order_id}] Triggering Fraud Detection")
    with grpc.insecure_channel("fraud_detection:50051") as channel:
        stub = fraud_detection_grpc.FraudDetectionStub(channel)
        fraud_resp = stub.ProcessOrder(fraud_detection.OrderProcessRequest(order_id=order_id))

    if fraud_resp.is_fraudulent:
        return {
            "orderId": order_id,
            "status": "Order Rejected (Fraud)",
            "suggestedBooks": []
        }

    # Get book suggestions
    with grpc.insecure_channel("suggestions:50053") as channel:
        stub = suggestions_grpc.SuggestionsStub(channel)
        sugg_resp = stub.GetBookSuggestions(suggestions.SuggestionsRequest(user_id=user_id, num_suggestions=5))

    return {
        "orderId": order_id,
        "status": "Order Approved",
        "suggestedBooks": [{"title": b} for b in sugg_resp.books]
    }

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
