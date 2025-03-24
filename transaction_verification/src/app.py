import os
import sys
import json
import logging
from concurrent import futures
import grpc
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils")))

from transaction_verification import transaction_verification_pb2 as txn
from transaction_verification import transaction_verification_pb2_grpc as txn_grpc
from vector_clock import VectorClock

# Setup logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

orders = {}

class TransactionVerificationService(txn_grpc.TransactionVerificationServicer):
    def ClearOrder(self, request, context):
        order_id = request.order_id
        final_clock = json.loads(request.final_clock)

        if order_id not in orders:
            return txn.ClearResponse(
                cleared=False,
                service="transaction_verification",
                error="Order not found"
            )

        local_clock = orders[order_id]["clock"].to_dict()

        # Compare vector clocks
        is_safe_to_clear = all(
            local_clock.get(s, 0) <= final_clock.get(s, 0)
            for s in final_clock
        )

        if is_safe_to_clear:
            del orders[order_id]
            logger.info(f"[{order_id}] Cleared successfully (VC ≤ VCf)")
            return txn.ClearResponse(
                cleared=True,
                service="transaction_verification",
                error=""
            )
        else:
            logger.warning(f"[{order_id}] Cannot clear: local VC > VCf")
            return txn.ClearResponse(
                cleared=False,
                service="transaction_verification",
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
            "results": {}
        }

        logger.info(f"[{order_id}] Cached order with initial clock: {clock}")
        return txn.CacheAck(message="Order cached")

    def ProcessOrder(self, request, context):
        order_id = request.order_id
        if order_id not in orders:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Order not found")
            return txn.TransactionVerificationResponse(is_valid=False, message="Order not found")

        state = orders[order_id]
        clock = state["clock"]
        data = state["data"]
        results = state["results"]

        logger.info(f"[{order_id}] Starting Transaction Verification Events")

        # Event (a): verify items
        def event_a():
            clock.increment("transaction_verification")
            items_ok = len(data.get("items", [])) > 0
            results['a'] = items_ok
            logger.info(f"[{order_id}] (a) Verify items → {items_ok} | clock={clock}")

        # Event (b): verify user info
        def event_b():
            clock.increment("transaction_verification")
            user = data.get("user", {})
            required = ["name", "contact"]
            user_ok = all(user.get(field) for field in required)
            results['b'] = user_ok
            logger.info(f"[{order_id}] (b) Verify user → {user_ok} | clock={clock}")

        # Event (c): verify credit card format (depends on a)
        def event_c():
            while 'a' not in results:
                pass  # wait for a to finish
            clock.increment("transaction_verification")
            cc = data.get("creditCard", {}).get("number", "")
            cc_ok = isinstance(cc, str) and len(cc) == 16 and cc.isdigit()
            results['c'] = cc_ok
            logger.info(f"[{order_id}] (c) Verify credit card → {cc_ok} | clock={clock}")

        t_a = threading.Thread(target=event_a)
        t_b = threading.Thread(target=event_b)
        t_c = threading.Thread(target=event_c)

        t_a.start()
        t_b.start()
        t_c.start()

        t_a.join()
        t_b.join()
        t_c.join()

        is_valid = all([results['a'], results['b'], results['c']])
        message = "Valid" if is_valid else "Invalid"

        logger.info(f"[{order_id}] Transaction result: {message} | Final Clock: {clock}")

        return txn.TransactionVerificationResponse(is_valid=is_valid, message=message)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    txn_grpc.add_TransactionVerificationServicer_to_server(TransactionVerificationService(), server)
    server.add_insecure_port("[::]:50052")
    logger.info("Transaction Verification Service running on port 50052")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
