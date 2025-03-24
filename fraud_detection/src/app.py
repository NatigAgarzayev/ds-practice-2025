import json
import random
from concurrent import futures
import grpc
import logging
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils")))

from fraud_detection import fraud_detection_pb2 as fraud
from fraud_detection import fraud_detection_pb2_grpc as fraud_grpc
from vector_clock import VectorClock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

orders = {}

class FraudDetectionService(fraud_grpc.FraudDetectionServicer):
    def CacheOrder(self, request, context):
        order_id = request.order_id
        orders[order_id] = {
            "data": json.loads(request.payload),
            "clock": VectorClock(["orchestrator", "transaction_verification", "fraud_detection"])
        }
        orders[order_id]["clock"].from_dict(json.loads(request.clock))
        logger.info(f"[{order_id}] Cached order and initialized vector clock")
        return fraud.CacheAck()

    def ProcessOrder(self, request, context):
        order_id = request.order_id
        cached = orders.get(order_id)
        data = cached["data"]
        clock = cached["clock"]

        # simulate fraud detection logic
        amount = data.get("amount")
        if amount is None:
            amount = sum(item.get("quantity", 1) * 20 for item in data.get("items", []))
        is_fraudulent = amount > 1000 or random.choice([False, True])

        clock.increment("fraud_detection")
        logger.info(f"[{order_id}] Fraud check complete: {'Fraud' if is_fraudulent else 'Legit'}")
        return fraud.FraudCheckResponse(is_fraudulent=is_fraudulent, message="done")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    fraud_grpc.add_FraudDetectionServicer_to_server(FraudDetectionService(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    logger.info("Fraud detection service running on port 50051")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
