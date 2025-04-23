import os
import sys
import time
import threading
import grpc
import logging
from concurrent import futures

# Fix import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from utils.pb.executor import executor_pb2_grpc, executor_pb2
from utils.pb.order_queue import order_queue_pb2_grpc, order_queue_pb2
from utils.pb.books_database import books_database_pb2_grpc, books_database_pb2

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("executor")

class ExecutorService(executor_pb2_grpc.ExecutorServicer):
    def __init__(self, executor_id, known_ids, queue_stub, db_stub):
        self.executor_id = executor_id
        self.known_ids = known_ids
        self.queue_stub = queue_stub
        self.db_stub = db_stub  # Database client
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
                        
                        # Process the order by calling the execute_order function
                        success = self.execute_order(
                            title=f"Book {response.order_id}", 
                            quantity=1,  # Assuming 1 book per order for simplicity
                            db_stub=self.db_stub
                        )
                        
                        if success:
                            logger.info(f"[{self.executor_id}] ✅ Order {response.order_id} executed successfully")
                        else:
                            logger.warning(f"[{self.executor_id}] ⚠️ Order {response.order_id} could not be executed")
                    else:
                        logger.info(f"[{self.executor_id}] 💤 No orders in queue. Waiting...")
                        time.sleep(2)
                except grpc.RpcError as e:
                    logger.error(f"[{self.executor_id}] ❌ Failed to contact queue service: {str(e)}")
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

    def execute_order(self, title, quantity, db_stub):
        """
        Execute an order by performing database operations.
        
        Args:
            title: Book title to order
            quantity: Number of copies to order
            db_stub: Database stub for communication
            
        Returns:
            bool: True if order was executed successfully, False otherwise
        """
        logger.info(f"[{self.executor_id}] Executing order for {quantity} copies of '{title}'")
        
        try:
            # Step 1: Read current stock
            response = db_stub.Read(books_database_pb2.ReadRequest(title=title))
            current_stock = response.stock
            logger.info(f"[{self.executor_id}] Current stock of '{title}': {current_stock}")
            
            # Step 2: Check stock availability
            if current_stock >= quantity:
                # Step 3: Write updated stock back to the database
                new_stock = current_stock - quantity
                write_response = db_stub.Write(books_database_pb2.WriteRequest(
                    title=title,
                    new_stock=new_stock
                ))
                
                logger.info(f"[{self.executor_id}] Updated stock of '{title}' to {new_stock}")
                return write_response.success
            else:
                logger.warning(f"[{self.executor_id}] Not enough stock for '{title}'. " 
                               f"Required: {quantity}, Available: {current_stock}")
                return False
        
        except Exception as e:
            logger.error(f"[{self.executor_id}] Error executing order: {str(e)}")
            return False

def serve():
    executor_id = os.environ["EXECUTOR_ID"]
    known_ids = os.environ["KNOWN_EXECUTORS"].split(",")

    # Connect to order queue
    queue_channel = grpc.insecure_channel("order_queue:50054")
    queue_stub = order_queue_pb2_grpc.OrderQueueStub(queue_channel)

    # Connect to books database (load balancer address)
    db_channel = grpc.insecure_channel("books_database_balancer:50056")
    db_stub = books_database_pb2_grpc.BooksDatabaseStub(db_channel)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    service = ExecutorService(executor_id, known_ids, queue_stub, db_stub)
    executor_pb2_grpc.add_ExecutorServicer_to_server(service, server)

    server.add_insecure_port("[::]:50055")
    server.start()
    logger.info(f"[{executor_id}] 🚀 Executor started on port 50055")

    threading.Thread(target=service.run).start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
