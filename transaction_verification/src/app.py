import json
from concurrent import futures
import grpc
import logging
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils")))

from transaction_verification import transaction_verification_pb2 as txn
from transaction_verification import transaction_verification_pb2_grpc as txn_grpc
from vector_clock import VectorClock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

orders = {}  # Cache for order data

class TransactionVerificationService(txn_grpc.TransactionVerificationServicer):
    def CacheOrder(self, request, context):
        order_id = request.order_id
        orders[order_id] = {
            "data": json.loads(request.payload),
            "clock": VectorClock(["orchestrator", "transaction_verification", "fraud_detection"])
        }
        orders[order_id]["clock"].from_dict(json.loads(request.clock))
        logger.info(f"[{order_id}] Cached order and initialized vector clock")
        return txn.CacheAck()

    def ProcessOrder(self, request, context):
        order_id = request.order_id
        cached = orders.get(order_id)
        clock = cached["clock"]
        data = cached["data"]

        user_id = data.get("user", {}).get("name", "")
        items = data.get("items", [])
        card = data.get("creditCard", {}).get("number", "")

        is_valid = user_id and items and len(card) == 16
        msg = "Valid" if is_valid else "Invalid"

        clock.increment("transaction_verification")
        logger.info(f"[{order_id}] Processed Transaction Verification - {msg}")
        return txn.TransactionVerificationResponse(is_valid=is_valid, message=msg)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    txn_grpc.add_TransactionVerificationServicer_to_server(TransactionVerificationService(), server)
    server.add_insecure_port("[::]:50052")
    server.start()
    logger.info("Transaction verification service running on port 50052")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
