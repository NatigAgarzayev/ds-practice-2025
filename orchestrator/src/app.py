import os
import sys
import json
import uuid
import logging
import threading
import grpc
from flask import Flask, request, jsonify
from flask_cors import CORS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "utils"))

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

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("orchestrator")

app = Flask(__name__)
CORS(app)

SERVICES = ["orchestrator",
            "transaction_verification",
            "fraud_detection",
            "suggestions"]


def broadcast_clear_order(order_id, final_clock):
    clock_json = json.dumps(final_clock.to_dict())
    results = {}

    def clear_txn():
        with grpc.insecure_channel("transaction_verification:50052") as ch:
            stub = txn_grpc.TransactionVerificationStub(ch)
            results["transaction_verification"] = stub.ClearOrder(
                txn.ClearRequest(order_id=order_id,
                                 final_clock=clock_json)
            )

    def clear_fraud():
        with grpc.insecure_channel("fraud_detection:50051") as ch:
            stub = fraud_grpc.FraudDetectionStub(ch)
            results["fraud_detection"] = stub.ClearOrder(
                fraud.ClearRequest(order_id=order_id,
                                   final_clock=clock_json)
            )

    def clear_suggestions():
        with grpc.insecure_channel("suggestions:50053") as ch:
            stub = sugg_grpc.SuggestionsStub(ch)
            results["suggestions"] = stub.ClearOrder(
                sugg.ClearRequest(order_id=order_id,
                                  final_clock=clock_json)
            )

    for fn in (clear_txn, clear_fraud, clear_suggestions):
        t = threading.Thread(target=fn)
        t.start()
        t.join()

    logger.info(f"[{order_id}] Broadcast clear results: {results}")


@app.route("/checkout", methods=["POST"])
def checkout():
    data     = request.get_json()
    order_id = str(uuid.uuid4())
    logger.info(f"[{order_id}] Checkout initiated")

    # 1) Vector clock bump
    clock = VectorClock(SERVICES)
    clock.increment("orchestrator")
    clock_json = json.dumps(clock.to_dict())

    # 2) Cache order in txn & fraud
    payload = json.dumps(data)
    with grpc.insecure_channel("transaction_verification:50052") as ch:
        txn_grpc.TransactionVerificationStub(ch).CacheOrder(
            txn.CachedOrderRequest(order_id=order_id, payload=payload, clock=clock_json)
        )
    with grpc.insecure_channel("fraud_detection:50051") as ch:
        fraud_grpc.FraudDetectionStub(ch).CacheOrder(
            fraud.CachedOrderRequest(order_id=order_id, payload=payload, clock=clock_json)
        )

    # 3) Transaction Verification
    with grpc.insecure_channel("transaction_verification:50052") as ch:
        resp = txn_grpc.TransactionVerificationStub(ch).ProcessOrder(
            txn.OrderProcessRequest(order_id=order_id)
        )
    if not resp.is_valid:
        return jsonify({"orderId": order_id, "status": "Order Rejected", "suggestedBooks": []})

    # 4) Fraud Detection
    with grpc.insecure_channel("fraud_detection:50051") as ch:
        resp = fraud_grpc.FraudDetectionStub(ch).ProcessOrder(
            fraud.OrderProcessRequest(order_id=order_id)
        )
    if resp.is_fraudulent:
        return jsonify({"orderId": order_id, "status": "Order Rejected (Fraud)", "suggestedBooks": []})

    # 5) Suggestions
    with grpc.insecure_channel("suggestions:50053") as ch:
        suggs = sugg_grpc.SuggestionsStub(ch).GetBookSuggestions(
            sugg.SuggestionsRequest(user_id=order_id, num_suggestions=5)
        )
    suggested = [{"title": b} for b in suggs.books]

    # 6) Atomic DecrementStock for each item
    with grpc.insecure_channel("books_db1:50060") as ch:
        db_stub = books_grpc.BooksDatabaseStub(ch)
        insufficient = []
        for item in data.get("items", []):
            title = item.get("title") or item.get("name")
            qty   = item.get("quantity", 0)
            dec   = db_stub.DecrementStock(books_pb2.DecrementRequest(
                title=title, amount=qty, order_id=order_id
            ))
            if not dec.success:
                insufficient.append((title, dec.new_stock, qty))
            else:
                logger.info(f"[{order_id}] Reserved {qty}×'{title}' → new_stock={dec.new_stock}")

    if insufficient:
        msg = "; ".join(f"{t}: have {have}, want {want}"
                        for t, have, want in insufficient)
        return jsonify({
            "orderId": order_id,
            "status":   "Order Rejected (Out of Stock)",
            "message":  msg,
            "suggestedBooks": []
        })

    logger.info(f"[{order_id}] Order Approved! Suggested books: {suggested}")

    # 7) Enqueue to OrderQueue
    with grpc.insecure_channel("order_queue:50054") as ch:
        queue_grpc.OrderQueueStub(ch).Enqueue(queue_pb2.OrderRequest(
            order_id=order_id,
            is_premium=data.get("user", {}).get("premium", False),
            shipping_method=data.get("shippingMethod", "Standard"),
            items=[ queue_pb2.Item(title=i.get("title") or i.get("name"), quantity=i.get("quantity",0))
                    for i in data.get("items", []) ]
        ))

    # 8) Clear caches
    broadcast_clear_order(order_id, clock)

    return jsonify({
        "orderId": order_id,
        "status":   "Order Approved",
        "suggestedBooks": suggested
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
