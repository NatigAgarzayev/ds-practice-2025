## Bonus: Handling Concurrent Writes

When two executors issue orders for the **same book** at the same time, we must prevent “oversell” while preserving high throughput. Below are several approaches—choose one or combine them with our existing 2PC staging:

---

### 1. Pessimistic Per‑Key Locking (Atomic Decrement)

**Idea:** Instead of a single global lock, maintain a **lock per book title**. Only one thread can update a given title at once, but different titles can proceed concurrently.

```python
# in DatabaseParticipant.__init__
self.key_locks = defaultdict(threading.Lock)

def DecrementStock(self, title, amount):
    lock = self.key_locks[title]
    with lock:  
        current, version = self.store.get(title, (0, 0))
        if current < amount:
            return DecrementResponse(success=False, new_stock=current)
        new_stock = current - amount
        new_version = version + 1
        self.store[title] = (new_stock, new_version)
        # replicate to backups...
    return DecrementResponse(success=True, new_stock=new_stock)

```

## Session 11 bonus.
### Quesiton:
What about failure of the coordinator? Analyse the system and try to understand what are the consequences of a failing coordinator, during the execution of the commitment protocol. Think of a solution for this issue. No implementation is needed, but the points will only be awarded upon good analysis, justification, and solution.

### Analysis and solution:
When the primary server crashes in the middle of the way, it may cause several problems:
* I lose data or receive only some parts of it.
* Client may get "Approved" but indeed it is failure.

In order to solve this issue we must have additional confirmation layer.
* Before applying write the primary server keeps it in a local disk log and sends "Prepare" message to each backup.
* Each backup then replies "Ready"
Then
* When we get all "Ready" it applies the changes in memory and mark it as done.
* Then sends to the user "Success" content.

For crash Recovery:
* On restart each node replays its log:
    - Any entry marked “Commit” is applied if not already.
    - Any entry stuck in “Prepare” without a matching “Commit” is rolled back.
* This ensures that we won't get half-written or lost info even though the coordinator failed.