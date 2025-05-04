import os
import sys
import threading
import heapq
import logging
from concurrent import futures

import grpc

# Ensure utils path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils")))

from utils.pb.order_queue import order_queue_pb2 as queue_pb2
from utils.pb.order_queue import order_queue_pb2_grpc as queue_grpc

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("order_queue")


class OrderQueueService(queue_grpc.OrderQueueServicer):
    def __init__(self):
        self._lock = threading.Lock()
        self._queue = []  # heapq priority queue

    def Enqueue(self, request, context):
        with self._lock:
            shipping_rank = {"Next-Day": 2, "Express": 1, "Standard": 0}
            priority = (
                -int(request.is_premium),                     # Premium users first
                -shipping_rank.get(request.shipping_method, 0),# Faster shipping first
                -len(request.items)                           # More items = higher priority
            )
            # Push (priority, order_id, items_list)
            heapq.heappush(self._queue, (priority, request.order_id, list(request.items)))

            logger.info(
                f"[{request.order_id}] 📨 Enqueued with priority {priority} "
                f"(premium={request.is_premium}, shipping='{request.shipping_method}', items={len(request.items)})"
            )

        return queue_pb2.QueueAck(success=True, message="Order enqueued with priority")

    def Dequeue(self, request, context):
        with self._lock:
            if self._queue:
                priority, order_id, items = heapq.heappop(self._queue)
                logger.info(f"[{order_id}] ✅ Dequeued | priority={priority}, items={len(items)}")
                return queue_pb2.OrderResponse(order_id=order_id, has_order=True, items=items)
            else:
                logger.info("[Queue] ❌ No orders to dequeue — waiting...")
                return queue_pb2.OrderResponse(order_id="", has_order=False)


def serve_queue_service():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    queue_grpc.add_OrderQueueServicer_to_server(OrderQueueService(), server)
    server.add_insecure_port("[::]:50054")
    logger.info("🚀 Order Queue Service running on port 50054")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve_queue_service()
