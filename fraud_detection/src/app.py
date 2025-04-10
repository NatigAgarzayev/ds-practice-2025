import os
import sys
import json
import logging
import threading
from concurrent import futures
import grpc

# ✅ Fix import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils")))

from utils.pb.fraud_detection import fraud_detection_pb2 as fraud
from utils.pb.fraud_detection import fraud_detection_pb2_grpc as fraud_grpc
from vector_clock import VectorClock

# ✅ Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

orders = {}

class FraudDetectionService(fraud_grpc.FraudDetectionServicer):
    def ClearOrder(self, request, context):
        order_id = request.order_id
        final_clock = json.loads(request.final_clock)

        if order_id not in orders:
            return fraud.ClearResponse(
                cleared=False,
                service="fraud_detection",
                error="Order not found"
            )

        local_clock = orders[order_id]["clock"].to_dict()
        is_safe_to_clear = all(
            local_clock.get(s, 0) <= final_clock.get(s, 0)
            for s in final_clock
        )

        if is_safe_to_clear:
            del orders[order_id]
            logger.info(f"[{order_id}] ✅ Cleared successfully (VC ≤ VCf) | local={local_clock}")
            return fraud.ClearResponse(cleared=True, service="fraud_detection", error="")
        else:
            logger.warning(f"[{order_id}] ❌ Cannot clear: local VC > VCf | local={local_clock}, final={final_clock}")
            return fraud.ClearResponse(
                cleared=False,
                service="fraud_detection",
                error="Vector clock conflict — cannot clear safely"
            )

    def CacheOrder(self, request, context):
        order_id = request.order_id
        data = json.loads(request.payload)
        clock = VectorClock(["orchestrator", "transaction_verification", "fraud_detection", "suggestions"])
        clock.from_dict(json.loads(request.clock))

        orders[order_id] = {
            "data": data,
            "clock": clock,
            "results": {},
            "upstream": {"b": True, "c": True}  # preload for demo
        }

        logger.info(f"[{order_id}] 📨 Cached fraud order. Initial clock: {clock}")
        return fraud.CacheAck(message="Order cached")

    def ProcessOrder(self, request, context):
        order_id = request.order_id
        if order_id not in orders:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Order not found")
            return fraud.FraudCheckResponse(is_fraudulent=False, message="Not found")

        state = orders[order_id]
        clock = state["clock"]
        data = state["data"]
        results = state["results"]

        logger.info(f"[{order_id}] 🧠 Starting Fraud Detection Events")

        def event_d():
            while 'b' not in state["upstream"]:
                pass
            clock.increment("fraud_detection")
            user = data.get("user", {})
            name = user.get("name", "").lower()
            email = user.get("contact", "").lower()

            is_fraud_user = (
                name in ["fraudy", "test user"] or
                email.endswith("@spam.com")
            )

            results["d"] = is_fraud_user
            logger.info(f"[{order_id}] (d) User fraud check → {is_fraud_user} | name={name}, email={email} | clock={clock}")

        def event_e():
            while 'c' not in state["upstream"] or 'd' not in results:
                pass
            clock.increment("fraud_detection")
            card = data.get("creditCard", {}).get("number", "")

            is_fraud_card = (
                card.startswith("0000") or
                len(card) != 16 or
                not card.isdigit()
            )

            results["e"] = is_fraud_card
            logger.info(f"[{order_id}] (e) Credit card fraud check → {is_fraud_card} | card={card} | clock={clock}")

        t_d = threading.Thread(target=event_d)
        t_e = threading.Thread(target=event_e)
        t_d.start()
        t_e.start()
        t_d.join()
        t_e.join()

        is_fraudulent = results.get("d", False) or results.get("e", False)
        msg = "Fraud detected" if is_fraudulent else "Legit"

        logger.info(f"[{order_id}] 🧾 Fraud Result → {msg} | Final Clock: {clock}")
        return fraud.FraudCheckResponse(is_fraudulent=is_fraudulent, message=msg)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    fraud_grpc.add_FraudDetectionServicer_to_server(FraudDetectionService(), server)
    server.add_insecure_port("[::]:50051")
    logger.info("🚀 Fraud Detection Service running on port 50051")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
