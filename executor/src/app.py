import os
import sys
import time
import threading
import grpc
import logging
from concurrent import futures
from grpc import StatusCode

# Fix import paths so we can load utils and generated pb files
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT)

# Executor and OrderQueue stubs
from utils.pb.executor       import executor_pb2, executor_pb2_grpc
from utils.pb.order_queue    import order_queue_pb2, order_queue_pb2_grpc
# BooksDatabase stubs (now with 2PC RPCs)
from utils.pb.books_database import (
    books_database_pb2       as books_pb2,
    books_database_pb2_grpc  as books_grpc
)
# PaymentService stubs
from utils.pb.payment       import payment_pb2, payment_pb2_grpc

from utils.vector_clock     import VectorClock

# Logging setup
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
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
        logger.info(f"[{self.executor_id}] 📢 New leader: {self.leader_id}")
        return executor_pb2.Ack(success=True, message="OK")

    def discover_peers(self):
        for peer in self.known_ids:
            if peer == self.executor_id:
                continue
            try:
                ch = grpc.insecure_channel(f"{peer}:50055")
                stub = executor_pb2_grpc.ExecutorStub(ch)
                stub.IsAlive(executor_pb2.Empty())
                self.alive_peers[peer] = stub
                logger.info(f"[{self.executor_id}] 🤝 Connected to {peer}")
            except grpc.RpcError:
                logger.warning(f"[{self.executor_id}] Cannot reach {peer}")

    def start_leader_election(self):
        logger.info(f"[{self.executor_id}] 🗳️ Leader election...")
        highest = self.executor_id
        for peer, stub in self.alive_peers.items():
            try:
                resp = stub.GetExecutorID(executor_pb2.Empty())
                if resp.id > highest:
                    highest = resp.id
            except:
                pass
        self.leader_id = highest
        logger.info(f"[{self.executor_id}] ✅ Elected leader: {self.leader_id}")
        for peer, stub in self.alive_peers.items():
            try:
                stub.AnnounceLeader(executor_pb2.ExecutorID(id=self.leader_id))
            except:
                pass

    def two_phase_commit(self, order_id, items):
        """
        Coordinate 2PC across PaymentService and BooksDatabase.
        Returns True if commit succeeded, False if aborted.
        """
        # --- prepare phase ---
        ready = True

        # 1) Payment prepare
        try:
            pay_ch = grpc.insecure_channel("payment:50061")
            pay_stub = payment_pb2_grpc.PaymentServiceStub(pay_ch)
            prep_resp = pay_stub.Prepare(
                payment_pb2.PrepareRequest(order_id=order_id,
                                          payload="{}")
            )
            if not prep_resp.ready:
                raise Exception("Payment not ready")
        except Exception as e:
            logger.warning(f"[{order_id}] Payment Prepare failed: {e}")
            ready = False

        # 2) Database prepare: stage each stock update
        db_ch = grpc.insecure_channel("books_db1:50060")
        db_stub = books_grpc.BooksDatabaseStub(db_ch)
        for item in items:
            if not ready:
                break
            try:
                # read current stock
                curr = db_stub.Read(books_pb2.ReadRequest(title=item.title)).stock
                new  = curr - item.quantity
                if new < 0:
                    raise Exception(f"Insufficient stock for {item.title}")
                # prepare staging
                db_stub.Prepare(books_pb2.PrepareRequest(
                    order_id=order_id,
                    title=item.title,
                    new_stock=new
                ))
            except Exception as e:
                logger.warning(f"[{order_id}] DB Prepare failed: {e}")
                ready = False

        # --- commit or abort ---
        if ready:
            logger.info(f"[{order_id}] All prepared → COMMIT")
            # commit payment
            try:
                pay_stub.Commit(payment_pb2.CommitRequest(order_id=order_id))
                logger.info(f"[{order_id}] 💰 Payment committed")
            except Exception as e:
                logger.error(f"[{order_id}] Payment Commit failed: {e}")
                ready = False

            # commit DB updates
            if ready:
                for item in items:
                    try:
                        db_stub.Commit(books_pb2.CommitRequest(
                            order_id=order_id,
                            title=item.title
                        ))
                        logger.info(f"[{order_id}] 💽 {item.title} committed")
                    except Exception as e:
                        logger.error(f"[{order_id}] DB Commit failed for {item.title}: {e}")
                        ready = False
                        break
        else:
            logger.info(f"[{order_id}] Prepare failed → ABORT")
            # abort payment
            try:
                pay_stub.Abort(payment_pb2.AbortRequest(order_id=order_id))
                logger.info(f"[{order_id}] 🚫 Payment aborted")
            except:
                pass
            # abort DB staging
            try:
                db_stub.Abort(books_pb2.AbortRequest(order_id=order_id))
                logger.info(f"[{order_id}] 🚫 DB aborted")
            except:
                pass

        return ready

    def run(self):
        time.sleep(3)
        self.discover_peers()
        self.start_leader_election()

        while True:
            if self.executor_id == self.leader_id:
                logger.info(f"[{self.executor_id}] 👑 Checking for orders...")
                try:
                    resp = self.queue_stub.Dequeue(order_queue_pb2.Empty())
                except grpc.RpcError as e:
                    logger.error(f"[{self.executor_id}] Queue RPC error: {e}")
                    time.sleep(2)
                    continue

                if not resp.has_order:
                    logger.info(f"[{self.executor_id}] 💤 No orders")
                    time.sleep(2)
                    continue

                order_id = resp.order_id
                logger.info(f"[{self.executor_id}] 🚚 2PC start for {order_id}")
                success = self.two_phase_commit(order_id, resp.items)
                if success:
                    logger.info(f"[{order_id}] ✅ Transaction committed")
                else:
                    logger.info(f"[{order_id}] ⚠️ Transaction aborted")
                time.sleep(1)
            else:
                logger.info(f"[{self.executor_id}] 🙅 Sleeping, not leader")
                time.sleep(3)


def serve():
    executor_id = os.environ["EXECUTOR_ID"]
    known_ids   = os.environ["KNOWN_EXECUTORS"].split(",")

    queue_ch   = grpc.insecure_channel("order_queue:50054")
    queue_stub = order_queue_pb2_grpc.OrderQueueStub(queue_ch)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    executor_pb2_grpc.add_ExecutorServicer_to_server(
        ExecutorService(executor_id, known_ids, queue_stub),
        server
    )
    server.add_insecure_port("[::]:50055")
    server.start()
    logger.info(f"[{executor_id}] 🚀 Executor gRPC listening on 50055")

    threading.Thread(target=server.wait_for_termination, daemon=True).start()

if __name__ == "__main__":
    serve()
