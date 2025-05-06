# Distributed System Project Documentation
### Here I showed key functionalities for checkpoint #3
---

## 1. `books_database/src/app.py`  
**Features:** Primary–Backup replication, Two‑Phase Commit participant, atomic `DecrementStock`

### Initialization

```python
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
...
```

### Replication (Primary → Backups)

```python
def Write(self, request, context):
    if self.db_id != self.peers[0]:
        context.abort(StatusCode.UNAVAILABLE,
                        f"Write only allowed on primary ({self.peers[0]})")
    with self.lock:
        self.clock.increment(self.db_id)
        self.store[request.title] = request.new_stock
    clock_json = json.dumps(self.clock.to_dict())
    logger.info(f"[{self.db_id}] ✏️ Local Write {request.title}→{request.new_stock}, VC={self.clock}")

    # replicate
    for peer in self.peers:
        if peer == self.db_id: continue
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
```


### Two‑Phase Commit Participant (2PC Participant RPCs)

```python
def Prepare(self, request, context):
    with self.lock:
        self.temp_updates[request.order_id] = (request.title, request.new_stock)
        self._append_log(request.order_id, request.title, request.new_stock)
    logger.info(f"[2PC Prepare] staged {request.title}→{request.new_stock} for {request.order_id}")
    return books_database_pb2.PrepareResponse(ready=True)

def Commit(self, request, context):
    with self.lock:
        tup = self.temp_updates.pop(request.order_id, None)
        if tup is None:
            context.abort(StatusCode.FAILED_PRECONDITION, "No staged update")
        title, new_stock = tup
        self.clock.increment(self.db_id)
        self.store[title] = new_stock
        self._remove_log(request.order_id)
    logger.info(f"[2PC Commit] applied {title}→{new_stock} for {request.order_id}, VC={self.clock}")
    return books_database_pb2.CommitResponse(success=True)

def Abort(self, request, context):
    with self.lock:
        removed = self.temp_updates.pop(request.order_id, None)
        if removed:
            self._remove_log(request.order_id)
    logger.info(f"[2PC Abort] cleared staging for {request.order_id}")
    return books_database_pb2.AbortResponse(aborted=True)
```

### Atomic Decrement (DecrementStock) - Session 10 bonus task
```python
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

        # perform update
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
```

## 2. `executor/src/app.py`  

### 2PC Coordinator + Leader Election

```python
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
...
```

### Two‑Phase Commit Orchestration

```python
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
...
```

## 3. `orchestrator/src/app.py`

### Checkout + Caching + Cleanup
``` python
@app.route("/checkout", methods=["POST"])
def checkout():
...
    # 2) Cache order in txn & fraud
    payload = json.dumps(data)
    with grpc.insecure_channel("transaction_verification:50052") as ch:
        stub = txn_grpc.TransactionVerificationStub(ch)
        stub.CacheOrder(txn.CachedOrderRequest(
            order_id=order_id, payload=payload, clock=clock_json
        ))
    with grpc.insecure_channel("fraud_detection:50051") as ch:
        stub = fraud_grpc.FraudDetectionStub(ch)
        stub.CacheOrder(fraud.CachedOrderRequest(
            order_id=order_id, payload=payload, clock=clock_json
        ))
    logger.info(f"[{order_id}] Order cached in transaction & fraud services.")
...
# 6) Inventory reservation in orchestrator (read + write)---
    db_ch   = grpc.insecure_channel("books_db1:50060")
    db_stub = books_grpc.BooksDatabaseStub(db_ch)

    insufficient = []
    for item in data.get("items", []):
        title    = item.get("title") or item.get("name")
        qty      = item.get("quantity", 0)
        # read current stock
        read_res = db_stub.Read(books_pb2.ReadRequest(title=title))
        current  = read_res.stock

        if current < qty:
            insufficient.append((title, current, qty))
            continue

        # reserve: write new stock
        new_stock = current - qty
        write_res = db_stub.Write(books_pb2.WriteRequest(
            title=title, new_stock=new_stock
        ))
        if not write_res.success:
            logger.error(f"[{order_id}] Failed to reserve stock for {title}")
            return jsonify({
                "orderId": order_id,
                "status":   "Order Failed",
                "message":  f"Could not reserve stock for {title}",
                "suggestedBooks": []
            }), 500

        logger.info(f"[{order_id}] Reserved {qty}×'{title}': {current}→{new_stock}")
...
if insufficient:
        msg = "; ".join(f"{t}: have {have}, want {want}"
                        for t, have, want in insufficient)
        logger.info(f"[{order_id}] Out of stock → Order Rejected ({msg})")
        return jsonify({
            "orderId": order_id,
            "status":   "Order Rejected (Out of Stock)",
            "message":  msg,
            "suggestedBooks": []
        }), 200
...
# 8) Clear cache
    broadcast_clear_order(order_id, clock)

    return jsonify({
        "orderId": order_id,
        "status":   "Order Approved",
        "suggestedBooks": suggested
    }), 200
```