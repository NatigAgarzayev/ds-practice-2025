import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import time
import threading
import grpc
from concurrent import futures

from utils.pb.executor import executor_pb2_grpc, executor_pb2
from utils.pb.order_queue import order_queue_pb2_grpc, order_queue_pb2


""" from utils.pb.executor import executor_pb2_grpc, executor_pb2
from utils.pb.order_queue import order_queue_pb2_grpc, order_queue_pb2 """

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
        print(f"[{self.executor_id}] New leader announced: {self.leader_id}")
        return executor_pb2.Ack(success=True, message="Acknowledged")

    def start_leader_election(self):
        print(f"[{self.executor_id}] Starting leader election...")
        highest_id = self.executor_id
        for peer_id, stub in self.alive_peers.items():
            try:
                response = stub.GetExecutorID(executor_pb2.Empty())
                if response.id > highest_id:
                    highest_id = response.id
            except Exception as e:
                print(f"[{self.executor_id}] Failed to reach {peer_id}")

        self.leader_id = highest_id
        print(f"[{self.executor_id}] Elected leader: {self.leader_id}")

        # Inform others
        for peer_id, stub in self.alive_peers.items():
            try:
                stub.AnnounceLeader(executor_pb2.ExecutorID(id=self.leader_id))
            except Exception:
                pass

    def run(self):
        # Delay to allow others to start
        time.sleep(3)
        self.discover_peers()
        self.start_leader_election()

        while True:
            if self.executor_id == self.leader_id:
                print(f"[{self.executor_id}] I am the leader. Checking for orders...")
                try:
                    response = self.queue_stub.Dequeue(order_queue_pb2.Empty())
                    if response.order_id:
                        print(f"[{self.executor_id}] Executing order: {response.order_id}")
                        time.sleep(2)  # simulate execution
                    else:
                        print(f"[{self.executor_id}] No orders. Waiting...")
                        time.sleep(2)
                except grpc.RpcError:
                    print(f"[{self.executor_id}] Failed to contact queue")
                    time.sleep(2)
            else:
                print(f"[{self.executor_id}] Not the leader ({self.leader_id}). Sleeping.")
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
                print(f"[{self.executor_id}] Connected to peer {peer_id}")
            except grpc.RpcError:
                print(f"[{self.executor_id}] Could not reach {peer_id}")


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
    print(f"[{executor_id}] Executor started on port 50055")
    
    # Run logic in background
    threading.Thread(target=service.run).start()

    server.wait_for_termination()

if __name__ == "__main__":
    serve()
