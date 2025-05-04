# books_database/src/app.py

import os
import sys
import json
import logging
import threading
import grpc
from concurrent import futures
from grpc import StatusCode

# Fix import paths
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "utils"))

from utils.vector_clock import VectorClock
from utils.pb.books_database import books_database_pb2_grpc, books_database_pb2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("books_db")


class DatabaseParticipant(books_database_pb2_grpc.BooksDatabaseServicer):
    def __init__(self, db_id, peers):
        self.db_id        = db_id
        self.peers        = peers
        self.store        = {}               # durable in-memory store
        self.clock        = VectorClock(peers)
        self.lock         = threading.Lock()
        self.temp_updates = {}               # staging area: order_id → (title, new_stock)
        self.log_path     = os.path.join(os.path.dirname(__file__), "staging_log.jsonl")

        # --- Load initial stock from JSON on startup: This is for the first BONUS session 11 ---
        init_path = os.path.join(os.path.dirname(__file__), "initial_stock.json")
        if os.path.exists(init_path):
            try:
                with open(init_path, "r") as f:
                    initial = json.load(f)
                with self.lock:
                    self.store.update(initial)
                logger.info(f"[{self.db_id}] Initial stock loaded: {initial}")
            except Exception as e:
                logger.error(f"[{self.db_id}] Failed to load initial stock: {e}")

        # Recover any in-doubt transactions from disk
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r") as f:
                    for line in f:
                        rec = json.loads(line)
                        self.temp_updates[rec["order_id"]] = (rec["title"], rec["new_stock"])
                logger.info(f"[{self.db_id}] Recovered {len(self.temp_updates)} staged txns from log")
            except Exception as e:
                logger.error(f"[{self.db_id}] Failed to recover staging log: {e}")

    def _append_log(self, order_id, title, new_stock):
        rec = {"order_id": order_id, "title": title, "new_stock": new_stock}
        with open(self.log_path, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def _remove_log(self, order_id):
        if not os.path.exists(self.log_path):
            return
        lines = []
        with open(self.log_path, "r") as f:
            for line in f:
                if json.loads(line)["order_id"] != order_id:
                    lines.append(line)
        with open(self.log_path, "w") as f:
            f.writelines(lines)

    # ---- Standard Read ----
    def Read(self, request, context):
        with self.lock:
            stock = self.store.get(request.title, 0)
        return books_database_pb2.ReadResponse(stock=stock)

    # ---- Primary → Backup Replication ----
    def Replicate(self, request, context):
        incoming = VectorClock(self.peers)
        incoming.from_dict(json.loads(request.clock))
        with self.lock:
            self.clock.merge(incoming)
            self.store[request.title] = request.new_stock
        logger.info(f"[{self.db_id}] 📥 Replicated {request.title}→{request.new_stock}, VC={incoming}")
        return books_database_pb2.ReplicateAck(success=True)

    # ---- 2PC Participant Methods ----
    def Prepare(self, request, context):
        """
        Stage the update for 2PC and persist to log.
        """
        with self.lock:
            self.temp_updates[request.order_id] = (request.title, request.new_stock)
            self._append_log(request.order_id, request.title, request.new_stock)
        logger.info(f"[2PC Prepare] staged {request.title}→{request.new_stock} for order {request.order_id}")
        return books_database_pb2.PrepareResponse(ready=True)

    def Commit(self, request, context):
        """
        Apply the staged update, advance the vector clock, and clean up log.
        """
        with self.lock:
            tup = self.temp_updates.pop(request.order_id, None)
            if tup is None:
                context.abort(StatusCode.FAILED_PRECONDITION, "No staged update")
            title, new_stock = tup
            # Actual execution happens here
            self.clock.increment(self.db_id)
            self.store[title] = new_stock
            self._remove_log(request.order_id)
            logger.info(f"[2PC Commit] applied {title}→{new_stock} for order {request.order_id}, VC={self.clock}")
        return books_database_pb2.CommitResponse(success=True)

    def Abort(self, request, context):
        """
        Discard the staged update and remove it from log.
        """
        with self.lock:
            removed = self.temp_updates.pop(request.order_id, None)
            if removed:
                self._remove_log(request.order_id)
        logger.info(f"[2PC Abort] cleared staging for order {request.order_id}")
        return books_database_pb2.AbortResponse(aborted=True)

    # ---- Direct Write (primary only) ----
    def Write(self, request, context):
        if self.db_id != self.peers[0]:
            primary = self.peers[0]
            context.abort(StatusCode.UNAVAILABLE, f"Write only allowed on primary: {primary}")
        with self.lock:
            self.clock.increment(self.db_id)
            self.store[request.title] = request.new_stock
        clock_json = json.dumps(self.clock.to_dict())
        logger.info(f"[{self.db_id}] ✏️ Local Write {request.title}→{request.new_stock}, VC={self.clock}")

        # replicate to backups
        for peer in self.peers:
            if peer == self.db_id:
                continue
            stub = books_database_pb2_grpc.BooksDatabaseStub(
                grpc.insecure_channel(f"{peer}:50060")
            )
            try:
                stub.Replicate(books_database_pb2.ReplicateRequest(
                    title=request.title,
                    new_stock=request.new_stock,
                    clock=clock_json
                ))
                logger.info(f"[{self.db_id}] ✅ Replicated to {peer}")
            except Exception as e:
                logger.warning(f"[{self.db_id}] ❌ Replicate to {peer} failed: {e}")

        return books_database_pb2.WriteResponse(success=True)


def serve():
    db_id = os.environ.get("DB_ID", "books_db1")
    peers = os.environ.get("KNOWN_DBS", "books_db1").split(",")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = DatabaseParticipant(db_id, peers)
    books_database_pb2_grpc.add_BooksDatabaseServicer_to_server(servicer, server)
    server.add_insecure_port("[::]:50060")
    server.start()
    logger.info(f"[{db_id}] 🚀 BooksDatabase (2PC + replication + recovery) listening on :50060")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
