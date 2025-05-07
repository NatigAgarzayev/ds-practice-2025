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
from utils.pb.books_database import (
    books_database_pb2_grpc,
    books_database_pb2
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("books_db")


class DatabaseParticipant(books_database_pb2_grpc.BooksDatabaseServicer):
    def __init__(self, db_id, peers):
        self.db_id        = db_id
        self.peers        = peers
        self.store        = {}               # durable in-memory store
        self.clock        = VectorClock(peers)
        self.lock         = threading.Lock()
        self.temp_updates = {}               # for 2PC staging
        self.log_path     = os.path.join(os.path.dirname(__file__), "staging_log.jsonl")

        # Load initial stock
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

        # Recover any in-doubt 2PC transactions
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r") as f:
                    for line in f:
                        rec = json.loads(line)
                        self.temp_updates.setdefault(rec["order_id"], []).append(
                            (rec["title"], rec["new_stock"])
                        )
                total = sum(len(v) for v in self.temp_updates.values())
                logger.info(f"[{self.db_id}] Recovered {total} staged updates")
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

    # ----- Standard RPCs -----

    def Read(self, request, context):
        with self.lock:
            stock = self.store.get(request.title, 0)
        return books_database_pb2.ReadResponse(stock=stock)

    def Write(self, request, context):
        if self.db_id != self.peers[0]:
            context.abort(StatusCode.UNAVAILABLE,
                          f"Write only allowed on primary ({self.peers[0]})")
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
                logger.warning(f"[{self.db_id}] ⚠️ Replicate to {peer} failed: {e}")
        return books_database_pb2.WriteResponse(success=True)

    def Replicate(self, request, context):
        incoming = VectorClock(self.peers)
        incoming.from_dict(json.loads(request.clock))
        with self.lock:
            self.clock.merge(incoming)
            self.store[request.title] = request.new_stock
        logger.info(f"[{self.db_id}] 📥 Replicated {request.title}→{request.new_stock}, VC={incoming}")
        return books_database_pb2.ReplicateAck(success=True)

    # ----- 2PC Participant RPCs -----

    def Prepare(self, request, context):
        with self.lock:
            self.temp_updates.setdefault(request.order_id, []).append(
                (request.title, request.new_stock)
            )
            self._append_log(request.order_id, request.title, request.new_stock)
        logger.info(f"[2PC Prepare] staged {request.title}→{request.new_stock} for order {request.order_id}")
        return books_database_pb2.PrepareResponse(ready=True)

    def Commit(self, request, context):
        with self.lock:
            staged = self.temp_updates.pop(request.order_id, [])
        if not staged:
            context.abort(StatusCode.FAILED_PRECONDITION, "No staged update")

        for title, new_stock in staged:
            with self.lock:
                self.clock.increment(self.db_id)
                self.store[title] = new_stock
            logger.info(f"[2PC Commit] applied {title}→{new_stock} for order {request.order_id}, VC={self.clock}")
            self._remove_log(request.order_id)

        return books_database_pb2.CommitResponse(success=True)

    def Abort(self, request, context):
        with self.lock:
            removed = self.temp_updates.pop(request.order_id, None)
            if removed:
                self._remove_log(request.order_id)
        logger.info(f"[2PC Abort] cleared staging for order {request.order_id}")
        return books_database_pb2.AbortResponse(aborted=True)

    # ----- New: Atomic DecrementStock RPC -----

    def DecrementStock(self, request, context):
        title  = request.title
        delta  = request.amount

        with self.lock:
            current = self.store.get(title, 0)
            if current < delta:
                return books_database_pb2.DecrementResponse(
                    success=False,
                    new_stock=current,
                    error=f"insufficient stock ({current} < {delta})"
                )

            new_stock = current - delta
            self.clock.increment(self.db_id)
            self.store[title] = new_stock
            clock_json = json.dumps(self.clock.to_dict())
            logger.info(
                f"[{self.db_id}] ✏️ Decrement '{title}' by {delta}: {current}→{new_stock}, VC={self.clock}"
            )

        # replicate to backups
        for peer in self.peers:
            if peer == self.db_id:
                continue
            stub = books_database_pb2_grpc.BooksDatabaseStub(
                grpc.insecure_channel(f"{peer}:50060")
            )
            try:
                stub.Replicate(books_database_pb2.ReplicateRequest(
                    title=title, new_stock=new_stock, clock=clock_json
                ))
                logger.info(f"[{self.db_id}] ✅ Replicated decrement to {peer}")
            except Exception as e:
                logger.warning(f"[{self.db_id}] ⚠️ Replicate to {peer} failed: {e}")

        return books_database_pb2.DecrementResponse(
            success=True,
            new_stock=new_stock,
            error=""
        )


def serve():
    db_id = os.environ.get("DB_ID", "books_db1")
    peers = os.environ.get("KNOWN_DBS", "books_db1").split(",")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = DatabaseParticipant(db_id, peers)
    books_database_pb2_grpc.add_BooksDatabaseServicer_to_server(servicer, server)
    server.add_insecure_port("[::]:50060")
    server.start()
    logger.info(f"[{db_id}] 🚀 BooksDatabase (2PC + repl + DecrementStock) on :50060")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
