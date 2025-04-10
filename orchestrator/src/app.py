import os
import sys
import json
import uuid
import logging
import threading
import grpc
from flask import Flask, request, jsonify
from flask_cors import CORS

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils")))

from utils.pb.transaction_verification import transaction_verification_pb2 as txn
from utils.pb.transaction_verification import transaction_verification_pb2_grpc as txn_grpc
from utils.pb.fraud_detection import fraud_detection_pb2 as fraud
from utils.pb.fraud_detection import fraud_detection_pb2_grpc as fraud_grpc
from utils.pb.suggestions import suggestions_pb2 as sugg
from utils.pb.suggestions import suggestions_pb2_grpc as sugg_grpc
from utils.pb.order_queue import order_queue_pb2 as queue_pb2
from utils.pb.order_queue import order_queue_pb2_grpc as queue_grpc

from vector_clock import VectorClock


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

SERVICES = ["orchestrator", "transaction_verification", "fraud_detection", "suggestions"]

def broadcast_clear_order(order_id, final_clock):
    clock_json = json.dumps(final_clock.to_dict())
    results = {}

    def clear_txn():
        with grpc.insecure_channel("transaction_verification:50052") as channel:
            stub = txn_grpc.TransactionVerificationStub(channel)
            resp = stub.ClearOrder(txn.ClearRequest(order_id=order_id, final_clock=clock_json))
            results["transaction_verification"] = resp

    def clear_fraud():
        with grpc.insecure_channel("fraud_detection:50051") as channel:
            stub = fraud_grpc.FraudDetectionStub(channel)
            resp = stub.ClearOrder(fraud.ClearRequest(order_id=order_id, final_clock=clock_json))
            results["fraud_detection"] = resp

    def clear_suggestions():
        with grpc.insecure_channel("suggestions:50053") as channel:
            stub = sugg_grpc.SuggestionsStub(channel)
            resp = stub.ClearOrder(sugg.ClearRequest(order_id=order_id, final_clock=clock_json))
            results["suggestions"] = resp

    threads = [
        threading.Thread(target=clear_txn),
        threading.Thread(target=clear_fraud),
        threading.Thread(target=clear_suggestions)
    ]

    for t in threads: t.start()
    for t in threads: t.join()

    logger.info(f"[{order_id}] Broadcast clear results:")
    for service, resp in results.items():
        logger.info(f"  - {service}: cleared={resp.cleared}, error={resp.error}")


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

    # 5. Enqueue order to the order queue (with priority fields)
    num_items = len(data.get("items", []))
    is_premium = data.get("user", {}).get("premium", False)
    shipping_method = data.get("shippingMethod", "Standard")

    with grpc.insecure_channel("order_queue:50054") as channel:
        stub = queue_grpc.OrderQueueStub(channel)
        ack = stub.Enqueue(queue_pb2.OrderRequest(
            order_id=order_id,
            num_items=num_items,
            is_premium=is_premium,
            shipping_method=shipping_method
        ))

        if not ack.success:
            logger.error(f"[{order_id}] Failed to enqueue: {ack.message}")
            return jsonify({
                "orderId": order_id,
                "status": "Failed to enqueue",
                "suggestedBooks": []
            })

        logger.info(f"[{order_id}] Successfully enqueued to OrderQueue with priority")


    # ✅ 6. Now broadcast to clear order data (after enqueue)
    broadcast_clear_order(order_id, clock)
    
    return jsonify({
        "orderId": order_id,
        "status": "Order Approved",
        "suggestedBooks": books
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)