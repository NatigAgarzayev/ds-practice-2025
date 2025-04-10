import os
import sys
import time
import threading
import grpc
import logging
from concurrent import futures

# ✅ Fix import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from utils.pb.executor import executor_pb2_grpc, executor_pb2
from utils.pb.order_queue import order_queue_pb2_grpc, order_queue_pb2

# ✅ Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("executor")

class ExecutorService(executor_pb2_grpc.ExecutorServicer):
    def __init__(self, executor_id, known_ids, queue_stub):
        self.executor_id = executor_id
        self.known_ids = known_ids
        self.queue_stub = queue_stub
        self.leader_id = None
        self.lock = threading.Lock()
        self.alive_peers = {}

    def GetExecutorID(self, request, context):
        return executor_pb2.ExecutorID(id=self.executor_id)

    def IsAlive(self, request, context):
        return executor_pb2.Ack(success=True, message="Alive")

    def AnnounceLeader(self, request, context):
        self.leader_id = request.id
        logger.info(f"[{self.executor_id}] 📢 New leader announced: {self.leader_id}")
        return executor_pb2.Ack(success=True, message="Acknowledged")

    def start_leader_election(self):
        logger.info(f"[{self.executor_id}] 🗳️ Starting leader election...")
        highest_id = self.executor_id

        for peer_id, stub in self.alive_peers.items():
            try:
                response = stub.GetExecutorID(executor_pb2.Empty())
                if response.id > highest_id:
                    highest_id = response.id
            except Exception:
                logger.warning(f"[{self.executor_id}] Could not reach {peer_id} during election")

        self.leader_id = highest_id
        logger.info(f"[{self.executor_id}] ✅ Elected leader: {self.leader_id}")

        for peer_id, stub in self.alive_peers.items():
            try:
                stub.AnnounceLeader(executor_pb2.ExecutorID(id=self.leader_id))
            except Exception:
                logger.warning(f"[{self.executor_id}] Could not notify {peer_id} about leader")

    def run(self):
        # Allow time for all replicas to boot up
        time.sleep(3)
        self.discover_peers()
        self.start_leader_election()

        while True:
            if self.executor_id == self.leader_id:
                logger.info(f"[{self.executor_id}] 👑 I am the leader. Checking for orders...")
                try:
                    response = self.queue_stub.Dequeue(order_queue_pb2.Empty())
                    if response.order_id:
                        logger.info(f"[{self.executor_id}] 🚚 Executing order: {response.order_id}")
                        time.sleep(2)  # simulate execution
                    else:
                        logger.info(f"[{self.executor_id}] 💤 No orders in queue. Waiting...")
                        time.sleep(2)
                except grpc.RpcError:
                    logger.error(f"[{self.executor_id}] ❌ Failed to contact queue service")
                    time.sleep(2)
            else:
                logger.info(f"[{self.executor_id}] 🙅 Not the leader (leader: {self.leader_id}). Sleeping...")
                time.sleep(3)

    def discover_peers(self):
        for peer_id in self.known_ids:
            if peer_id == self.executor_id:
                continue
            try:
                channel = grpc.insecure_channel(f"{peer_id}:50055")
                stub = executor_pb2_grpc.ExecutorStub(channel)
                stub.IsAlive(executor_pb2.Empty())
                self.alive_peers[peer_id] = stub
                logger.info(f"[{self.executor_id}] 🤝 Connected to peer: {peer_id}")
            except grpc.RpcError:
                logger.warning(f"[{self.executor_id}] Could not connect to peer: {peer_id}")

def serve():
    executor_id = os.environ["EXECUTOR_ID"]
    known_ids = os.environ["KNOWN_EXECUTORS"].split(",")

    queue_channel = grpc.insecure_channel("order_queue:50054")
    queue_stub = order_queue_pb2_grpc.OrderQueueStub(queue_channel)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    service = ExecutorService(executor_id, known_ids, queue_stub)
    executor_pb2_grpc.add_ExecutorServicer_to_server(service, server)

    server.add_insecure_port("[::]:50055")
    server.start()
    logger.info(f"[{executor_id}] 🚀 Executor started on port 50055")

    threading.Thread(target=service.run).start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
