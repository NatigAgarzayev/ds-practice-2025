# payment/src/app.py

import os
import sys
import logging
import grpc
from concurrent import futures
from grpc import StatusCode

# Ensure we can import utils & generated stubs
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "utils"))

from utils.pb.payment import payment_pb2, payment_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("payment")

class PaymentService(payment_pb2_grpc.PaymentServiceServicer):
    def __init__(self):
        # orders in “prepared” state
        self.prepared = set()
        # orders already executed
        self.executed = set()

    def Prepare(self, request, context):
        logger.info(f"[Prepare] staging payment for order {request.order_id}")
        self.prepared.add(request.order_id)
        return payment_pb2.PrepareResponse(ready=True)

    def Commit(self, request, context):
        if request.order_id not in self.prepared:
            context.abort(StatusCode.FAILED_PRECONDITION, "Order not prepared")
        # --- actual execution only on commit ---
        logger.info(f"[Commit] executing payment for order {request.order_id}")
        # (dummy logic: e.g. debit a balance map here)
        self.executed.add(request.order_id)
        # clean up
        self.prepared.remove(request.order_id)
        return payment_pb2.CommitResponse(success=True)

    def Abort(self, request, context):
        if request.order_id in self.prepared:
            logger.info(f"[Abort] discarding staged payment for order {request.order_id}")
            self.prepared.remove(request.order_id)
        return payment_pb2.AbortResponse(aborted=True)

def serve():
    port = os.getenv("PAYMENT_PORT", "50061")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(PaymentService(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info(f"🚀 PaymentService listening on port {port}")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
