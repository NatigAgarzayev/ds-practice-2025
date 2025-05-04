import os
import sys
import time
import threading
import grpc
import logging
from concurrent import futures
from grpc import StatusCode

# Fix import paths so we can load utils and generated pb files
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")) )

from utils.pb.executor         import executor_pb2_grpc, executor_pb2
from utils.pb.order_queue      import order_queue_pb2, order_queue_pb2_grpc
from utils.pb.books_database   import books_database_pb2 as books_pb2, books_database_pb2_grpc as books_grpc
from utils.vector_clock        import VectorClock

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("executor")


class ExecutorService(executor_pb2_grpc.ExecutorServicer):
    def __init__(self, executor_id, known_ids, queue_stub):
        self.executor_id = executor_id
        self.known_ids   = known_ids
        self.queue_stub  = queue_stub
        self.leader_id   = None
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
                resp = stub.GetExecutorID(executor_pb2.Empty())
                if resp.id > highest_id:
                    highest_id = resp.id
            except grpc.RpcError:
                logger.warning(f"[{self.executor_id}] Could not reach {peer_id}")
        self.leader_id = highest_id
        logger.info(f"[{self.executor_id}] ✅ Elected leader: {self.leader_id}")
        for peer_id, stub in self.alive_peers.items():
            try:
                stub.AnnounceLeader(executor_pb2.ExecutorID(id=self.leader_id))
            except grpc.RpcError:
                logger.warning(f"[{self.executor_id}] Could not notify {peer_id}")

    def discover_peers(self):
        for peer_id in self.known_ids:
            if peer_id == self.executor_id:
                continue
            try:
                ch = grpc.insecure_channel(f"{peer_id}:50055")
                stub = executor_pb2_grpc.ExecutorStub(ch)
                stub.IsAlive(executor_pb2.Empty())
                self.alive_peers[peer_id] = stub
                logger.info(f"[{self.executor_id}] 🤝 Connected to peer: {peer_id}")
            except grpc.RpcError:
                logger.warning(f"[{self.executor_id}] Could not connect to peer: {peer_id}")

    def run(self):
        # allow time for all replicas
        time.sleep(3)
        self.discover_peers()
        self.start_leader_election()

        while True:
            if self.executor_id == self.leader_id:
                logger.info(f"[{self.executor_id}] 👑 I am the leader. Checking for orders...")
                try:
                    response = self.queue_stub.Dequeue(order_queue_pb2.Empty())
                    if response.has_order:
                        logger.info(f"[{self.executor_id}] 🚚 Executing order: {response.order_id}")

                        # Connect to the Primary BooksDatabase
                        db_ch   = grpc.insecure_channel("books_db1:50060")
                        db_stub = books_grpc.BooksDatabaseStub(db_ch)

                        # For each item in the order, read & decrement stock
                        for item in response.items:
                            # 1) Read current stock
                            read_resp = db_stub.Read(books_pb2.ReadRequest(title=item.title))
                            current = read_resp.stock

                            # 2) Validate and Write new stock
                            if current >= item.quantity:
                                new_stock = current - item.quantity
                                write_resp = db_stub.Write(books_pb2.WriteRequest(
                                    title=item.title, new_stock=new_stock
                                ))
                                if write_resp.success:
                                    logger.info(
                                        f"[{self.executor_id}] 💽 {item.title}: {current} → {new_stock}"
                                    )
                                else:
                                    logger.error(
                                        f"[{self.executor_id}] ❌ Write failed for {item.title}"
                                    )
                            else:
                                logger.warning(
                                    f"[{self.executor_id}] ⚠️ Not enough stock for {item.title} "
                                    f"(have {current}, want {item.quantity})"
                                )

                        logger.info(f"[{self.executor_id}] ✅ Finished order {response.order_id}")
                        time.sleep(1)
                    else:
                        logger.info(f"[{self.executor_id}] 💤 No orders. Sleeping...")
                        time.sleep(2)

                except grpc.RpcError as e:
                    logger.error(f"[{self.executor_id}] ❌ Queue RPC failed: {e}")
                    time.sleep(2)

            else:
                logger.info(f"[{self.executor_id}] 🙅 Not the leader. Sleeping...")
                time.sleep(3)


def serve():
    executor_id = os.environ["EXECUTOR_ID"]
    known_ids   = os.environ["KNOWN_EXECUTORS"].split(",")

    # Queue stub for Dequeue()
    queue_ch   = grpc.insecure_channel("order_queue:50054")
    queue_stub = order_queue_pb2_grpc.OrderQueueStub(queue_ch)

    # Start the gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = ExecutorService(executor_id, known_ids, queue_stub)
    executor_pb2_grpc.add_ExecutorServicer_to_server(servicer, server)
    server.add_insecure_port("[::]:50055")
    server.start()
    logger.info(f"[{executor_id}] 🚀 Executor gRPC server started on port 50055")

    # Start the execution loop in a background thread
    threading.Thread(target=servicer.run, daemon=True).start()

    server.wait_for_termination()


if __name__ == "__main__":
    serve()
