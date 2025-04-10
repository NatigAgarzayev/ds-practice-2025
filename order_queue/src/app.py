import grpc
import threading
import time
from concurrent import futures
import sys
import os
import heapq # for bonus task

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils")))

from utils.pb.order_queue import order_queue_pb2 as queue_pb2
from utils.pb.order_queue import order_queue_pb2_grpc as queue_grpc


class OrderQueueService(queue_grpc.OrderQueueServicer):
    def __init__(self):
        self._lock = threading.Lock()
        self._queue = []  # heapq priority queue

    def Enqueue(self, request, context):
        with self._lock:
            # Assign a numeric rank for shipping
            shipping_rank = {"Next-Day": 2, "Express": 1, "Standard": 0}
            priority = (
                -int(request.is_premium),                             # Premium users go first
                -shipping_rank.get(request.shipping_method, 0),       # Faster shipping gets priority
                -request.num_items                                    # More items → higher priority
            )
            heapq.heappush(self._queue, (priority, request.order_id))
            print(f"[Queue] Enqueued with priority {priority}: {request.order_id}")
        return queue_pb2.QueueAck(success=True, message="Order enqueued with priority")

    def Dequeue(self, request, context):
        with self._lock:
            if self._queue:
                _, order_id = heapq.heappop(self._queue)
                print(f"[Queue] Dequeued order: {order_id}")
                return queue_pb2.OrderResponse(order_id=order_id, has_order=True)
            else:
                return queue_pb2.OrderResponse(order_id="", has_order=False)


def serve_queue_service():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    queue_grpc.add_OrderQueueServicer_to_server(OrderQueueService(), server)
    server.add_insecure_port("[::]:50054")  # Choose any unused port
    print("Order Queue Service running on port 50054")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve_queue_service()