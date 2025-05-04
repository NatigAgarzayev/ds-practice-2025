import os
import sys
import json
import time
import grpc
import logging
from concurrent import futures
from grpc import StatusCode

# Fix import paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from utils.vector_clock import VectorClock
from utils.pb.books_database import (
    books_database_pb2_grpc,
    books_database_pb2
)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("books_db")


class BaseBooksDatabaseServicer(books_database_pb2_grpc.BooksDatabaseServicer):
    def __init__(self, db_id, peers):
        self.db_id = db_id
        self.peers = peers
        self.store = {}             # in-memory key→stock
        self.clock = VectorClock(peers)

        # --- New: load initial stock from JSON ---
        init_path = os.path.join(os.path.dirname(__file__), "initial_stock.json")
        if os.path.exists(init_path):
            try:
                with open(init_path, "r") as f:
                    initial = json.load(f)
                for title, stock in initial.items():
                    self.store[title] = stock
                logger.info(f"[{self.db_id}] Initial stock loaded: {self.store}")
            except Exception as e:
                logger.error(f"[{self.db_id}] Failed to load initial stock: {e}")

    def Read(self, request, context):
        """Return current stock (default 0 if missing)."""
        stock = self.store.get(request.title, 0)
        return books_database_pb2.ReadResponse(stock=stock)

    def Replicate(self, request, context):
        """
        Called by the primary to update backups.
        Merges vector clocks and applies the write.
        """
        incoming = VectorClock(self.peers)
        incoming.from_dict(json.loads(request.clock))
        self.clock.merge(incoming)
        self.store[request.title] = request.new_stock
        logger.info(f"[{self.db_id}] 📥 Replicated '{request.title}' → {request.new_stock}, VC={incoming}")
        return books_database_pb2.ReplicateAck(success=True)


class PrimaryReplica(BaseBooksDatabaseServicer):
    def Write(self, request, context):
        """
        1) Update local state & VC
        2) Synchronously send Replicate RPCs to all backups, with retries
        """
        # 1) Local update
        self.clock.increment(self.db_id)
        self.store[request.title] = request.new_stock
        clock_json = json.dumps(self.clock.to_dict())
        logger.info(f"[{self.db_id}] ✏️ Local Write '{request.title}' → {request.new_stock}, VC={self.clock}")

        # 2) Propagate with ACK & retry
        max_retries = 3
        for peer in self.peers:
            if peer == self.db_id:
                continue
            stub = books_database_pb2_grpc.BooksDatabaseStub(
                grpc.insecure_channel(f"{peer}:50060")
            )
            for attempt in range(1, max_retries + 1):
                try:
                    ack = stub.Replicate(
                        books_database_pb2.ReplicateRequest(
                            title=request.title,
                            new_stock=request.new_stock,
                            clock=clock_json
                        )
                    )
                    if ack.success:
                        logger.info(f"[{self.db_id}] ✅ Replicate to {peer} succeeded on attempt {attempt}")
                        break
                except Exception as e:
                    logger.warning(f"[{self.db_id}] ❌ Replicate to {peer} failed (attempt {attempt}): {e}")
                time.sleep(0.5)  # backoff

        return books_database_pb2.WriteResponse(success=True)


class BackupReplica(BaseBooksDatabaseServicer):
    def Write(self, request, context):
        """
        Backups do not accept client writes.
        """
        primary = self.peers[0]
        context.abort(
            StatusCode.UNAVAILABLE,
            f"Write not allowed on backup. Please retry against primary: {primary}"
        )


def serve():
    db_id = os.environ["DB_ID"]
    peers = os.environ["KNOWN_DBS"].split(",")
    is_primary = (db_id == peers[0])

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    if is_primary:
        servicer = PrimaryReplica(db_id, peers)
        logger.info(f"[{db_id}] 🏷️ Role=PRIMARY")
    else:
        servicer = BackupReplica(db_id, peers)
        logger.info(f"[{db_id}] 🏷️ Role=BACKUP")

    books_database_pb2_grpc.add_BooksDatabaseServicer_to_server(servicer, server)
    server.add_insecure_port("[::]:50060")
    server.start()
    logger.info(f"[{db_id}] 🚀 Serving on port 50060")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
