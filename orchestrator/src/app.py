import os
import sys
import json
import uuid
import logging
import threading
import grpc
from flask import Flask, request, jsonify
from flask_cors import CORS

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils")))

from transaction_verification import transaction_verification_pb2 as txn
from transaction_verification import transaction_verification_pb2_grpc as txn_grpc
from fraud_detection import fraud_detection_pb2 as fraud
from fraud_detection import fraud_detection_pb2_grpc as fraud_grpc
from suggestions import suggestions_pb2 as sugg
from suggestions import suggestions_pb2_grpc as sugg_grpc
from vector_clock import VectorClock

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

SERVICES = ["orchestrator", "transaction_verification", "fraud_detection", "suggestions"]

@app.route("/checkout", methods=["POST"])
def checkout():
    data = request.get_json()
    order_id = str(uuid.uuid4())
    logger.info(f"[{order_id}] Checkout initiated")

    clock = VectorClock(SERVICES)
    clock.increment("orchestrator")

    payload = json.dumps(data)
    clock_json = json.dumps(clock.to_dict())

    # 1. Send to cache all services
    def cache_txn():
        with grpc.insecure_channel("transaction_verification:50052") as channel:
            stub = txn_grpc.TransactionVerificationStub(channel)
            stub.CacheOrder(txn.CachedOrderRequest(order_id=order_id, payload=payload, clock=clock_json))

    def cache_fraud():
        with grpc.insecure_channel("fraud_detection:50051") as channel:
            stub = fraud_grpc.FraudDetectionStub(channel)
            stub.CacheOrder(fraud.CachedOrderRequest(order_id=order_id, payload=payload, clock=clock_json))

    cache_txn()
    cache_fraud()
    logger.info(f"[{order_id}] Order cached in services.")

    # 2. Trigger Transaction Verification ProcessOrder (a, b, c)
    with grpc.insecure_channel("transaction_verification:50052") as channel:
        stub = txn_grpc.TransactionVerificationStub(channel)
        verify_result = stub.ProcessOrder(txn.OrderProcessRequest(order_id=order_id))

    if not verify_result.is_valid:
        logger.info(f"[{order_id}] Transaction invalid → Order Rejected")
        return jsonify({
            "orderId": order_id,
            "status": "Order Rejected",
            "suggestedBooks": []
        })

    # 3. Trigger Fraud Detection ProcessOrder (d, e)
    with grpc.insecure_channel("fraud_detection:50051") as channel:
        stub = fraud_grpc.FraudDetectionStub(channel)
        fraud_result = stub.ProcessOrder(fraud.OrderProcessRequest(order_id=order_id))

    if fraud_result.is_fraudulent:
        logger.info(f"[{order_id}] Fraud detected → Order Rejected")
        return jsonify({
            "orderId": order_id,
            "status": "Order Rejected (Fraud)",
            "suggestedBooks": []
        })

    # 4. Trigger Book Suggestions (f)
    with grpc.insecure_channel("suggestions:50053") as channel:
        stub = sugg_grpc.SuggestionsStub(channel)
        suggs = stub.GetBookSuggestions(sugg.SuggestionsRequest(user_id=order_id, num_suggestions=5))

    books = [{"title": b} for b in suggs.books]
    logger.info(f"[{order_id}] Order Approved! Suggested books: {books}")

    return jsonify({
        "orderId": order_id,
        "status": "Order Approved",
        "suggestedBooks": books
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
