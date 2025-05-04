import os
import sys
import json
import uuid
import logging
import threading
import grpc
from flask import Flask, request, jsonify
from flask_cors import CORS

# Fix import paths so we can load utils and generated pb files
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "utils"))

# gRPC stubs
from utils.pb.transaction_verification import (
    transaction_verification_pb2 as txn,
    transaction_verification_pb2_grpc as txn_grpc
)
from utils.pb.fraud_detection import (
    fraud_detection_pb2 as fraud,
    fraud_detection_pb2_grpc as fraud_grpc
)
from utils.pb.suggestions import (
    suggestions_pb2 as sugg,
    suggestions_pb2_grpc as sugg_grpc
)
from utils.pb.order_queue import (
    order_queue_pb2 as queue_pb2,
    order_queue_pb2_grpc as queue_grpc
)
from utils.pb.books_database import (
    books_database_pb2 as books_pb2,
    books_database_pb2_grpc as books_grpc
)

from utils.vector_clock import VectorClock

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("orchestrator")

app = Flask(__name__)
CORS(app)

SERVICES = ["orchestrator", "transaction_verification", "fraud_detection", "suggestions"]

def broadcast_clear_order(order_id, final_clock):
    clock_json = json.dumps(final_clock.to_dict())
    results = {}

    def clear_txn():
        with grpc.insecure_channel("transaction_verification:50052") as ch:
            stub = txn_grpc.TransactionVerificationStub(ch)
            results["transaction_verification"] = stub.ClearOrder(
                txn.ClearRequest(order_id=order_id, final_clock=clock_json)
            )

    def clear_fraud():
        with grpc.insecure_channel("fraud_detection:50051") as ch:
            stub = fraud_grpc.FraudDetectionStub(ch)
            results["fraud_detection"] = stub.ClearOrder(
                fraud.ClearRequest(order_id=order_id, final_clock=clock_json)
            )

    def clear_suggestions():
        with grpc.insecure_channel("suggestions:50053") as ch:
            stub = sugg_grpc.SuggestionsStub(ch)
            results["suggestions"] = stub.ClearOrder(
                sugg.ClearRequest(order_id=order_id, final_clock=clock_json)
            )

    threads = [
        threading.Thread(target=clear_txn),
        threading.Thread(target=clear_fraud),
        threading.Thread(target=clear_suggestions)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    logger.info(f"[{order_id}] Broadcast clear results: { {svc: vars(resp) for svc, resp in results.items()} }")

@app.route("/checkout", methods=["POST"])
def checkout():
    data     = request.get_json()
    order_id = str(uuid.uuid4())
    logger.info(f"[{order_id}] Checkout initiated")

    # 1) Vector clock bump
    clock = VectorClock(SERVICES)
    clock.increment("orchestrator")
    logger.info(f"[{order_id}] Initial Vector Clock: {clock}")
    clock_json = json.dumps(clock.to_dict())

    # 2) Cache order in txn & fraud
    payload = json.dumps(data)
    with grpc.insecure_channel("transaction_verification:50052") as ch:
        stub = txn_grpc.TransactionVerificationStub(ch)
        stub.CacheOrder(txn.CachedOrderRequest(
            order_id=order_id, payload=payload, clock=clock_json
        ))
    with grpc.insecure_channel("fraud_detection:50051") as ch:
        stub = fraud_grpc.FraudDetectionStub(ch)
        stub.CacheOrder(fraud.CachedOrderRequest(
            order_id=order_id, payload=payload, clock=clock_json
        ))
    logger.info(f"[{order_id}] Order cached in transaction & fraud services.")

    # 3) Transaction Verification
    with grpc.insecure_channel("transaction_verification:50052") as ch:
        stub = txn_grpc.TransactionVerificationStub(ch)
        verify = stub.ProcessOrder(txn.OrderProcessRequest(order_id=order_id))
    if not verify.is_valid:
        logger.info(f"[{order_id}] Transaction invalid → Order Rejected")
        return jsonify({"orderId": order_id, "status": "Order Rejected", "suggestedBooks": []}), 200

    # 4) Fraud Detection
    with grpc.insecure_channel("fraud_detection:50051") as ch:
        stub = fraud_grpc.FraudDetectionStub(ch)
        fraud_res = stub.ProcessOrder(fraud.OrderProcessRequest(order_id=order_id))
    if fraud_res.is_fraudulent:
        logger.info(f"[{order_id}] Fraud detected → Order Rejected")
        return jsonify({"orderId": order_id, "status": "Order Rejected (Fraud)", "suggestedBooks": []}), 200

    # 5) Book Suggestions
    with grpc.insecure_channel("suggestions:50053") as ch:
        stub = sugg_grpc.SuggestionsStub(ch)
        suggs = stub.GetBookSuggestions(sugg.SuggestionsRequest(
            user_id=order_id, num_suggestions=5
        ))
    suggested = [{"title": b} for b in suggs.books]
    logger.info(f"[{order_id}] Order Approved! Suggested books: {suggested}")

    # 6) Inventory validation against BooksDatabase
    db_stub = books_grpc.BooksDatabaseStub(
        grpc.insecure_channel("books_db1:50060")
    )
    insufficient = []
    for item in data.get("items", []):
        title    = item.get("title") or item.get("name")
        quantity = item.get("quantity", 0)
        read_res = db_stub.Read(books_pb2.ReadRequest(title=title))
        if read_res.stock < quantity:
            insufficient.append((title, read_res.stock, quantity))

    if insufficient:
        msg = "; ".join(f"{t}: have {have}, want {want}" for t, have, want in insufficient)
        logger.info(f"[{order_id}] Out of stock → Order Rejected ({msg})")
        return jsonify({
            "orderId": order_id,
            "status": "Order Rejected (Out of Stock)",
            "message": msg,
            "suggestedBooks": []
        }), 200

    # 7) Enqueue to OrderQueue
    items_msgs = [
        queue_pb2.Item(
            title=item.get("title") or item.get("name"),
            quantity=item.get("quantity", 0)
        )
        for item in data.get("items", [])
    ]
    with grpc.insecure_channel("order_queue:50054") as ch:
        stub = queue_grpc.OrderQueueStub(ch)
        ack = stub.Enqueue(queue_pb2.OrderRequest(
            order_id=order_id,
            is_premium=data.get("user", {}).get("premium", False),
            shipping_method=data.get("shippingMethod", "Standard"),
            items=items_msgs
        ))
    if not ack.success:
        logger.error(f"[{order_id}] Failed to enqueue: {ack.message}")
        return jsonify({"orderId": order_id, "status": "Failed to enqueue", "suggestedBooks": []}), 500
    logger.info(f"[{order_id}] Successfully enqueued to OrderQueue")

    # 8) Clear cache
    broadcast_clear_order(order_id, clock)

    return jsonify({
        "orderId": order_id,
        "status": "Order Approved",
        "suggestedBooks": suggested
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
