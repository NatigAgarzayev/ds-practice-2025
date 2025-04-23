import os
import sys
import time
import threading
import grpc
import logging
from concurrent import futures
import random
import json

# Fix import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

# Import the generated gRPC modules
from utils.pb.books_database import books_database_pb2_grpc, books_database_pb2

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("books_database")

class ChainReplicationReplica(books_database_pb2_grpc.BooksDatabaseServicer, 
                           books_database_pb2_grpc.ReplicaSyncServicer):
    def __init__(self, replica_id, known_replicas):
        """
        Initialize the database replica with chain replication protocol.
        
        Args:
            replica_id: Unique identifier for this replica
            known_replicas: List of all replica IDs in the system
        """
        self.replica_id = replica_id
        self.known_replicas = known_replicas
        self.lock = threading.RLock()
        self.data = {}  # The key-value store: {book_title: stock_count}
        self.version_vectors = {}  # Version vectors for each key: {book_title: {replica_id: version}}
        self.replica_stubs = {}  # For connecting to other replicas
        
        # Chain replication specific state
        self.chain_position = -1  # Will be determined during chain formation
        self.predecessor = None  # Replica before this one in the chain
        self.successor = None    # Replica after this one in the chain
        self.is_head = False     # True if this is the head of the chain
        self.is_tail = False     # True if this is the tail of the chain
        self.pending_writes = [] # Buffer of writes waiting to be propagated
        
        # Initialize with sample data if this is a new replica
        self._initialize_sample_data()
        
        # Connect to other replicas and form the chain
        self._connect_to_peers()
        
        # Start chain formation after a short delay to ensure connections are established
        threading.Timer(2.0, self._form_chain).start()
        
        # Start background thread to handle chain maintenance
        threading.Thread(target=self._chain_maintenance_loop, daemon=True).start()
        
        logger.info(f"[{self.replica_id}] 📚 Books Database Chain Replica initialized")
        
    def _initialize_sample_data(self):
        """Initialize the database with sample book data if not already populated"""
        sample_books = {
            "The Great Gatsby": 10,
            "To Kill a Mockingbird": 15,
            "1984": 8,
            "Pride and Prejudice": 12,
            "The Hobbit": 20
        }
        
        with self.lock:
            # Only initialize if the database is empty
            if not self.data:
                self.data = sample_books
                # Initialize version vectors for each book
                for book in self.data:
                    self.version_vectors[book] = {self.replica_id: 1}
                
                logger.info(f"[{self.replica_id}] 📚 Initialized with {len(self.data)} sample books")
                
    def _connect_to_peers(self):
        """Establish gRPC connections to other replicas"""
        for replica_id in self.known_replicas:
            if replica_id != self.replica_id:
                try:
                    # Create channel to the other replica
                    channel = grpc.insecure_channel(f"{replica_id}:50056")
                    stub = books_database_pb2_grpc.ReplicaSyncStub(channel)
                    
                    # Test connection with a simple status check
                    response = stub.GetStatus(books_database_pb2.StatusRequest())
                    if response.is_alive:
                        self.replica_stubs[replica_id] = stub
                        logger.info(f"[{self.replica_id}] 🔄 Connected to replica: {replica_id}")
                except Exception as e:
                    logger.warning(f"[{self.replica_id}] ⚠️ Could not connect to replica {replica_id}: {str(e)}")
    
    def _form_chain(self):
        """Form the replication chain by ordering replicas alphabetically"""
        # Use sorted list of replica IDs to determine chain order
        sorted_replicas = sorted(list(self.replica_stubs.keys()) + [self.replica_id])
        logger.info(f"[{self.replica_id}] Forming chain with replicas: {sorted_replicas}")
        
        # Find this replica's position in the chain
        self.chain_position = sorted_replicas.index(self.replica_id)
        
        # Set predecessor (if not head)
        if self.chain_position > 0:
            self.predecessor = sorted_replicas[self.chain_position - 1]
        else:
            self.is_head = True
            logger.info(f"[{self.replica_id}] 👑 This replica is the HEAD of the chain")
            
        # Set successor (if not tail)
        if self.chain_position < len(sorted_replicas) - 1:
            self.successor = sorted_replicas[self.chain_position + 1]
        else:
            self.is_tail = True
            logger.info(f"[{self.replica_id}] 🔚 This replica is the TAIL of the chain")
            
        logger.info(f"[{self.replica_id}] Chain formed: position={self.chain_position}, "
                    f"predecessor={self.predecessor}, successor={self.successor}")
        
        # Sync state with chain members if not head (head has the authoritative state)
        if not self.is_head:
            self._sync_state_from_predecessor()
    
    def _sync_state_from_predecessor(self):
        """Get the current state from the predecessor in the chain"""
        if not self.predecessor or self.predecessor not in self.replica_stubs:
            logger.warning(f"[{self.replica_id}] Cannot sync state: predecessor not available")
            return
            
        try:
            # This would require extending the proto with a GetFullState method
            # For now, we simulate by getting each key individually through read requests
            for key in list(self.data.keys()):
                read_req = books_database_pb2.ReadRequest(title=key)
                response = self.replica_stubs[self.predecessor].Read(read_req)
                if response.success:
                    with self.lock:
                        self.data[key] = response.stock
                        # Here we'd also update version vectors, but we're simplifying
            logger.info(f"[{self.replica_id}] ✅ Synced state from predecessor {self.predecessor}")
        except Exception as e:
            logger.error(f"[{self.replica_id}] ❌ Failed to sync state from predecessor: {str(e)}")
    
    def _chain_maintenance_loop(self):
        """Periodically check chain health and reform if needed"""
        while True:
            # Check if successor and predecessor are still available
            chain_valid = True
            
            if self.successor and self.successor not in self.replica_stubs:
                logger.warning(f"[{self.replica_id}] Successor {self.successor} not available")
                chain_valid = False
                
            if self.predecessor and self.predecessor not in self.replica_stubs:
                logger.warning(f"[{self.replica_id}] Predecessor {self.predecessor} not available")
                chain_valid = False
            
            # Refresh connections to peers
            self._connect_to_peers()
            
            # If chain is broken, reform it
            if not chain_valid:
                logger.info(f"[{self.replica_id}] Chain broken, reforming...")
                self._form_chain()
                
            # Process any pending writes
            self._process_pending_writes()
                
            time.sleep(5)  # Check every 5 seconds
    
    def _process_pending_writes(self):
        """Process any pending writes that need to be propagated"""
        with self.lock:
            if not self.pending_writes:
                return
                
            if not self.successor or self.successor not in self.replica_stubs:
                logger.warning(f"[{self.replica_id}] Cannot propagate {len(self.pending_writes)} pending writes: no successor")
                return
                
            # Try to propagate each pending write
            remaining_writes = []
            for write in self.pending_writes:
                try:
                    title, new_stock, version_vector = write
                    sync_request = books_database_pb2.SyncWriteRequest(
                        title=title,
                        new_stock=new_stock,
                        timestamp=int(time.time() * 1000)  # Current time as timestamp
                    )
                    # We would need to add version_vector to the SyncWriteRequest in the proto
                    # For now, just use timestamp
                    
                    response = self.replica_stubs[self.successor].SyncWrite(sync_request)
                    if not response.success:
                        logger.warning(f"[{self.replica_id}] Failed to propagate write for {title}: {response.message}")
                        remaining_writes.append(write)
                except Exception as e:
                    logger.error(f"[{self.replica_id}] Error propagating write for {title}: {str(e)}")
                    remaining_writes.append(write)
                    
            # Update pending writes list with those that failed
            self.pending_writes = remaining_writes
            if remaining_writes:
                logger.warning(f"[{self.replica_id}] {len(remaining_writes)} writes still pending propagation")
            else:
                logger.info(f"[{self.replica_id}] All pending writes successfully propagated")
            
    def Read(self, request, context):
        """
        Handle a read request for a book's stock.
        In Chain Replication, consistent reads come from the tail.
        
        Args:
            request: ReadRequest with the book title
            context: gRPC context
            
        Returns:
            ReadResponse with the current stock value
        """
        title = request.title
        logger.info(f"[{self.replica_id}] 📖 Read request for book: {title}")
        
        # In chain replication, consistent reads should come from the tail
        # If this is not the tail and we want strict consistency, forward to the tail
        if not self.is_tail and self.successor and self.successor in self.replica_stubs:
            try:
                # Forward read to the tail through the chain
                return self.replica_stubs[self.successor].Read(request)
            except Exception as e:
                logger.error(f"[{self.replica_id}] ❌ Failed to forward read to successor: {str(e)}")
                # Fall back to local read if forwarding fails
                logger.warning(f"[{self.replica_id}] Falling back to local read (might be stale)")
        
        # Perform local read (either we're the tail or forwarding failed)
        with self.lock:
            if title in self.data:
                return books_database_pb2.ReadResponse(
                    stock=self.data[title],
                    success=True,
                    message="Book found"
                )
            else:
                return books_database_pb2.ReadResponse(
                    stock=0,
                    success=False,
                    message="Book not found"
                )
                
    def Write(self, request, context):
        """
        Handle a write request to update a book's stock.
        In Chain Replication, writes enter at the head and propagate to the tail.
        
        Args:
            request: WriteRequest with the book title and new stock value
            context: gRPC context
            
        Returns:
            WriteResponse indicating success or failure
        """
        title = request.title
        new_stock = request.new_stock
        
        logger.info(f"[{self.replica_id}] ✏️ Write request for book: {title}, new stock: {new_stock}")
        
        # In chain replication, writes must be sent to the head of the chain
        if not self.is_head and self.predecessor and self.predecessor in self.replica_stubs:
            try:
                # Forward write to the head (or predecessor in chain)
                return self.replica_stubs[self.predecessor].Write(request)
            except Exception as e:
                logger.error(f"[{self.replica_id}] ❌ Failed to forward write to predecessor: {str(e)}")
                return books_database_pb2.WriteResponse(
                    success=False,
                    message=f"Failed to forward write to head of chain: {str(e)}"
                )
        
        # Process write at head of chain
        with self.lock:
            # Update local state
            self.data[title] = new_stock
            
            # Update version vector
            if title not in self.version_vectors:
                self.version_vectors[title] = {}
            if self.replica_id not in self.version_vectors[title]:
                self.version_vectors[title][self.replica_id] = 0
            self.version_vectors[title][self.replica_id] += 1
            
            # If this is not the tail, propagate to successor
            if not self.is_tail:
                if self.successor and self.successor in self.replica_stubs:
                    try:
                        sync_request = books_database_pb2.SyncWriteRequest(
                            title=title,
                            new_stock=new_stock,
                            timestamp=int(time.time() * 1000)  # Current time
                        )
                        # In a full implementation, we'd include version vector
                        
                        response = self.replica_stubs[self.successor].SyncWrite(sync_request)
                        if response.success:
                            return books_database_pb2.WriteResponse(
                                success=True,
                                message="Write operation successful and propagating through chain"
                            )
                        else:
                            # Store in pending writes for later retry
                            self.pending_writes.append((title, new_stock, self.version_vectors[title].copy()))
                            return books_database_pb2.WriteResponse(
                                success=True,
                                message="Write accepted but synchronization delayed"
                            )
                    except Exception as e:
                        # Store in pending writes for later retry
                        self.pending_writes.append((title, new_stock, self.version_vectors[title].copy()))
                        logger.error(f"[{self.replica_id}] Failed to propagate write: {str(e)}")
                        return books_database_pb2.WriteResponse(
                            success=True,
                            message="Write accepted but synchronization delayed"
                        )
                else:
                    # No successor available, store in pending writes
                    self.pending_writes.append((title, new_stock, self.version_vectors[title].copy()))
                    return books_database_pb2.WriteResponse(
                        success=True,
                        message="Write accepted but cannot be propagated (no successor)"
                    )
            else:
                # This is the tail, write is complete through the chain
                return books_database_pb2.WriteResponse(
                    success=True,
                    message="Write operation successful through entire chain"
                )
                
    def SyncWrite(self, request, context):
        """
        Handle a synchronization write request from predecessor in the chain.
        
        Args:
            request: SyncWriteRequest with book title, new stock, and timestamp
            context: gRPC context
            
        Returns:
            SyncWriteResponse indicating success or failure
        """
        title = request.title
        new_stock = request.new_stock
        timestamp = request.timestamp
        
        logger.info(f"[{self.replica_id}] 🔄 Sync write from predecessor for book: {title}")
        
        with self.lock:
            # Apply the write locally
            self.data[title] = new_stock
            
            # Update version vector (simplified)
            if title not in self.version_vectors:
                self.version_vectors[title] = {}
            if self.predecessor not in self.version_vectors[title]:
                self.version_vectors[title][self.predecessor] = 0
            self.version_vectors[title][self.predecessor] += 1
            
            # If not tail, propagate to successor
            if not self.is_tail:
                if self.successor and self.successor in self.replica_stubs:
                    try:
                        # Forward to next replica in chain
                        response = self.replica_stubs[self.successor].SyncWrite(request)
                        if response.success:
                            return books_database_pb2.SyncWriteResponse(
                                success=True,
                                message="Sync write forwarded through chain"
                            )
                        else:
                            # Store in pending writes
                            self.pending_writes.append((title, new_stock, self.version_vectors[title].copy()))
                            return books_database_pb2.SyncWriteResponse(
                                success=True,
                                message="Sync write accepted but forwarding delayed"
                            )
                    except Exception as e:
                        # Store in pending writes
                        self.pending_writes.append((title, new_stock, self.version_vectors[title].copy()))
                        logger.error(f"[{self.replica_id}] ❌ Failed to forward sync write: {str(e)}")
                        return books_database_pb2.SyncWriteResponse(
                            success=True,
                            message="Sync write accepted but forwarding delayed"
                        )
                else:
                    # No successor, store in pending writes
                    self.pending_writes.append((title, new_stock, self.version_vectors[title].copy()))
                    return books_database_pb2.SyncWriteResponse(
                        success=True,
                        message="Sync write accepted but cannot be forwarded (no successor)"
                    )
            
            # This is the tail, sync is complete
            return books_database_pb2.SyncWriteResponse(
                success=True,
                message="Sync write completed through chain"
            )
                
    def GetStatus(self, request, context):
        """
        Check if this replica is alive and ready for operations.
        
        Args:
            request: StatusRequest
            context: gRPC context
            
        Returns:
            StatusResponse indicating if the replica is alive
        """
        return books_database_pb2.StatusResponse(is_alive=True)

    # Add these new methods to the BooksDatabaseReplica class
    def IncrementStock(self, request, context):
        """
        Atomically increment a book's stock by the specified amount.
        
        Args:
            request: IncrementRequest with book title and increment amount
            context: gRPC context
            
        Returns:
            StockOperationResponse with success status and new stock value
        """
        title = request.title
        amount = request.amount
        
        logger.info(f"[{self.replica_id}] ➕ Increment stock request for book: {title}, amount: {amount}")
        
        with self.lock:
            # Get current stock or initialize to 0 if book doesn't exist
            old_stock = self.data.get(title, 0)
            new_stock = old_stock + amount
            
            # Update data
            self.data[title] = new_stock
            
            # Update timestamp
            timestamp = int(time.time() * 1000)
            self.write_timestamps[title] = timestamp
            
            # Sync with other replicas
            sync_success = self._sync_increment_to_replicas(title, amount, timestamp)
            
            return books_database_pb2.StockOperationResponse(
                success=True,
                message=f"Stock incremented by {amount}" + 
                        ("" if sync_success else " (sync incomplete)"),
                new_stock=new_stock,
                old_stock=old_stock
            )
            
    def DecrementStock(self, request, context):
        """
        Atomically decrement a book's stock by the specified amount.
        
        Args:
            request: DecrementRequest with book title, decrement amount, and behavior flag
            context: gRPC context
            
        Returns:
            StockOperationResponse with success status and new stock value
        """
        title = request.title
        amount = request.amount
        fail_if_insufficient = request.fail_if_insufficient
        
        logger.info(f"[{self.replica_id}] ➖ Decrement stock request for book: {title}, amount: {amount}")
        
        with self.lock:
            # Get current stock or initialize to 0 if book doesn't exist
            old_stock = self.data.get(title, 0)
            new_stock = old_stock - amount
            
            # Check if this would make stock negative
            if new_stock < 0 and fail_if_insufficient:
                return books_database_pb2.StockOperationResponse(
                    success=False,
                    message=f"Insufficient stock: have {old_stock}, requested {amount}",
                    new_stock=old_stock,
                    old_stock=old_stock
                )
                
            # Update data
            self.data[title] = new_stock
            
            # Update timestamp
            timestamp = int(time.time() * 1000)
            self.write_timestamps[title] = timestamp
            
            # Sync with other replicas
            sync_success = self._sync_decrement_to_replicas(title, amount, fail_if_insufficient, timestamp)
            
            return books_database_pb2.StockOperationResponse(
                success=True,
                message=f"Stock decremented by {amount}" + 
                        ("" if sync_success else " (sync incomplete)"),
                new_stock=new_stock,
                old_stock=old_stock
            )
            
    def CompareAndSwap(self, request, context):
        """
        Perform an atomic compare-and-swap operation on a book's stock.
        
        Args:
            request: CompareAndSwapRequest with book title, expected stock, and new stock
            context: gRPC context
            
        Returns:
            StockOperationResponse with success status and new stock value
        """
        title = request.title
        expected_stock = request.expected_stock
        new_stock = request.new_stock
        
        logger.info(f"[{self.replica_id}] 🔄 Compare-and-swap request for book: {title}, "
                f"expected: {expected_stock}, new: {new_stock}")
        
        with self.lock:
            # Get current stock
            current_stock = self.data.get(title, 0)
            
            # Check if current stock matches expected value
            if current_stock != expected_stock:
                return books_database_pb2.StockOperationResponse(
                    success=False,
                    message=f"Current stock ({current_stock}) does not match expected ({expected_stock})",
                    new_stock=current_stock,
                    old_stock=current_stock
                )
                
            # Update data
            self.data[title] = new_stock
            
            # Update timestamp
            timestamp = int(time.time() * 1000)
            self.write_timestamps[title] = timestamp
            
            # Sync with other replicas
            sync_success = self._sync_cas_to_replicas(title, expected_stock, new_stock, timestamp)
            
            return books_database_pb2.StockOperationResponse(
                success=True,
                message=f"Stock updated from {expected_stock} to {new_stock}" + 
                        ("" if sync_success else " (sync incomplete)"),
                new_stock=new_stock,
                old_stock=expected_stock
            )
            
    def BulkRead(self, request, context):
        """
        Read multiple book stocks in a single operation.
        
        Args:
            request: BulkReadRequest with list of book titles
            context: gRPC context
            
        Returns:
            BulkReadResponse with stock values for each book
        """
        titles = request.titles
        logger.info(f"[{self.replica_id}] 📚 Bulk read request for {len(titles)} books")
        
        with self.lock:
            result = {}
            for title in titles:
                result[title] = self.data.get(title, 0)
                
            return books_database_pb2.BulkReadResponse(
                success=True,
                message=f"Read {len(titles)} books",
                stocks=result
            )
            
    def SearchBooks(self, request, context):
        """
        Search for books by partial title match, filtered by minimum stock.
        
        Args:
            request: SearchRequest with search query and filters
            context: gRPC context
            
        Returns:
            SearchResponse with matching book information
        """
        query = request.query.lower()
        min_stock = request.min_stock
        max_results = request.max_results if request.max_results > 0 else float('inf')
        
        logger.info(f"[{self.replica_id}] 🔍 Search request: '{query}', min stock: {min_stock}, max results: {max_results}")
        
        with self.lock:
            results = []
            for title, stock in self.data.items():
                if (query in title.lower() and stock >= min_stock):
                    results.append(books_database_pb2.BookInfo(
                        title=title,
                        stock=stock
                    ))
                    
                    if len(results) >= max_results:
                        break
                        
            return books_database_pb2.SearchResponse(
                success=True,
                message=f"Found {len(results)} matching books",
                results=results
            )
            
    def GetStockMetrics(self, request, context):
        """
        Calculate and return metrics about the current book inventory.
        
        Args:
            request: MetricsRequest with filtering options
            context: gRPC context
            
        Returns:
            MetricsResponse with various stock metrics
        """
        include_zero_stock = request.include_zero_stock
        
        logger.info(f"[{self.replica_id}] 📊 Stock metrics request (include zero stock: {include_zero_stock})")
        
        with self.lock:
            # Filter books based on include_zero_stock
            books_to_consider = self.data.items()
            if not include_zero_stock:
                books_to_consider = [(title, stock) for title, stock in books_to_consider if stock > 0]
                
            if not books_to_consider:
                return books_database_pb2.MetricsResponse(
                    success=True,
                    message="No books available for metrics calculation",
                    total_books=0,
                    total_stock=0,
                    average_stock=0,
                    min_stock=0,
                    max_stock=0,
                    most_stocked_title="",
                    least_stocked_title=""
                )
                
            # Calculate metrics
            total_books = len(books_to_consider)
            total_stock = sum(stock for _, stock in books_to_consider)
            average_stock = total_stock // total_books if total_books > 0 else 0
            
            # Find min/max stock and corresponding titles
            min_stock_item = min(books_to_consider, key=lambda x: x[1])
            max_stock_item = max(books_to_consider, key=lambda x: x[1])
            min_stock = min_stock_item[1]
            max_stock = max_stock_item[1]
            least_stocked_title = min_stock_item[0]
            most_stocked_title = max_stock_item[0]
            
            return books_database_pb2.MetricsResponse(
                success=True,
                message="Metrics calculated successfully",
                total_books=total_books,
                total_stock=total_stock,
                average_stock=average_stock,
                min_stock=min_stock,
                max_stock=max_stock,
                most_stocked_title=most_stocked_title,
                least_stocked_title=least_stocked_title
            )

    # Synchronization methods for new operations

    def _sync_increment_to_replicas(self, title, amount, timestamp):
        """
        Propagate an increment operation to all other replicas.
        
        Args:
            title: Book title (the key)
            amount: Amount to increment by
            timestamp: Timestamp of the operation
            
        Returns:
            bool: True if sync was successful with majority of replicas
        """
        successful_syncs = 0
        total_replicas = len(self.replica_stubs)
        
        # Phase 1: Check if all replicas are available
        available_replicas = {}
        for replica_id, stub in self.replica_stubs.items():
            try:
                response = stub.GetStatus(books_database_pb2.StatusRequest())
                if response.is_alive:
                    available_replicas[replica_id] = stub
                    logger.debug(f"[{self.replica_id}] Replica {replica_id} is available for sync")
            except Exception as e:
                logger.warning(f"[{self.replica_id}] Replica {replica_id} is not available: {str(e)}")
                
        # Phase 2: If majority of replicas are available, proceed with sync
        if len(available_replicas) >= (total_replicas // 2):
            for replica_id, stub in available_replicas.items():
                try:
                    sync_request = books_database_pb2.SyncIncrementRequest(
                        title=title,
                        amount=amount,
                        timestamp=timestamp
                    )
                    response = stub.SyncIncrement(sync_request)
                    if response.success:
                        successful_syncs += 1
                        logger.debug(f"[{self.replica_id}] Successfully synced increment to {replica_id}")
                    else:
                        logger.warning(f"[{self.replica_id}] Failed to sync increment to {replica_id}: {response.message}")
                except Exception as e:
                    logger.error(f"[{self.replica_id}] Error syncing increment to {replica_id}: {str(e)}")
            
            logger.info(f"[{self.replica_id}] Increment sync completed: {successful_syncs}/{len(available_replicas)} successful")
            return successful_syncs >= (len(available_replicas) // 2)  # Success if majority synced
        else:
            logger.warning(f"[{self.replica_id}] Not enough replicas available for sync")
            return False

    def _sync_decrement_to_replicas(self, title, amount, fail_if_insufficient, timestamp):
        """
        Propagate a decrement operation to all other replicas.
        
        Args:
            title: Book title (the key)
            amount: Amount to decrement by
            fail_if_insufficient: Whether to fail if stock would become negative
            timestamp: Timestamp of the operation
            
        Returns:
            bool: True if sync was successful with majority of replicas
        """
        successful_syncs = 0
        total_replicas = len(self.replica_stubs)
        
        # Phase 1: Check if all replicas are available
        available_replicas = {}
        for replica_id, stub in self.replica_stubs.items():
            try:
                response = stub.GetStatus(books_database_pb2.StatusRequest())
                if response.is_alive:
                    available_replicas[replica_id] = stub
                    logger.debug(f"[{self.replica_id}] Replica {replica_id} is available for sync")
            except Exception as e:
                logger.warning(f"[{self.replica_id}] Replica {replica_id} is not available: {str(e)}")
                
        # Phase 2: If majority of replicas are available, proceed with sync
        if len(available_replicas) >= (total_replicas // 2):
            for replica_id, stub in available_replicas.items():
                try:
                    sync_request = books_database_pb2.SyncDecrementRequest(
                        title=title,
                        amount=amount,
                        fail_if_insufficient=fail_if_insufficient,
                        timestamp=timestamp
                    )
                    response = stub.SyncDecrement(sync_request)
                    if response.success:
                        successful_syncs += 1
                        logger.debug(f"[{self.replica_id}] Successfully synced decrement to {replica_id}")
                    else:
                        logger.warning(f"[{self.replica_id}] Failed to sync decrement to {replica_id}: {response.message}")
                except Exception as e:
                    logger.error(f"[{self.replica_id}] Error syncing decrement to {replica_id}: {str(e)}")
            
            logger.info(f"[{self.replica_id}] Decrement sync completed: {successful_syncs}/{len(available_replicas)} successful")
            return successful_syncs >= (len(available_replicas) // 2)  # Success if majority synced
        else:
            logger.warning(f"[{self.replica_id}] Not enough replicas available for sync")
            return False

    def _sync_cas_to_replicas(self, title, expected_stock, new_stock, timestamp):
        """
        Propagate a compare-and-swap operation to all other replicas.
        
        Args:
            title: Book title (the key)
            expected_stock: Expected current stock value
            new_stock: New stock value to set
            timestamp: Timestamp of the operation
            
        Returns:
            bool: True if sync was successful with majority of replicas
        """
        successful_syncs = 0
        total_replicas = len(self.replica_stubs)
        
        # Phase 1: Check if all replicas are available
        available_replicas = {}
        for replica_id, stub in self.replica_stubs.items():
            try:
                response = stub.GetStatus(books_database_pb2.StatusRequest())
                if response.is_alive:
                    available_replicas[replica_id] = stub
                    logger.debug(f"[{self.replica_id}] Replica {replica_id} is available for sync")
            except Exception as e:
                logger.warning(f"[{self.replica_id}] Replica {replica_id} is not available: {str(e)}")
                
        # Phase 2: If majority of replicas are available, proceed with sync
        if len(available_replicas) >= (total_replicas // 2):
            for replica_id, stub in available_replicas.items():
                try:
                    sync_request = books_database_pb2.SyncCompareAndSwapRequest(
                        title=title,
                        expected_stock=expected_stock,
                        new_stock=new_stock,
                        timestamp=timestamp
                    )
                    response = stub.SyncCompareAndSwap(sync_request)
                    if response.success:
                        successful_syncs += 1
                        logger.debug(f"[{self.replica_id}] Successfully synced CAS to {replica_id}")
                    else:
                        logger.warning(f"[{self.replica_id}] Failed to sync CAS to {replica_id}: {response.message}")
                except Exception as e:
                    logger.error(f"[{self.replica_id}] Error syncing CAS to {replica_id}: {str(e)}")
            
            logger.info(f"[{self.replica_id}] CAS sync completed: {successful_syncs}/{len(available_replicas)} successful")
            return successful_syncs >= (len(available_replicas) // 2)  # Success if majority synced
        else:
            logger.warning(f"[{self.replica_id}] Not enough replicas available for sync")
            return False

    # Add these sync handlers to the ReplicaSyncServicer part

    def SyncIncrement(self, request, context):
        """
        Handle a synchronization increment request from another replica.
        
        Args:
            request: SyncIncrementRequest with book title, amount, and timestamp
            context: gRPC context
            
        Returns:
            SyncWriteResponse indicating success or failure
        """
        title = request.title
        amount = request.amount
        timestamp = request.timestamp
        
        logger.info(f"[{self.replica_id}] 🔄 Sync increment request from another replica for book: {title}")
        
        with self.lock:
            current_timestamp = self.write_timestamps.get(title, 0)
            
            # Apply write if it has a newer or equal timestamp
            if timestamp >= current_timestamp:
                current_stock = self.data.get(title, 0)
                self.data[title] = current_stock + amount
                self.write_timestamps[title] = timestamp
                return books_database_pb2.SyncWriteResponse(
                    success=True,
                    message="Sync increment applied successfully"
                )
            else:
                return books_database_pb2.SyncWriteResponse(
                    success=False,
                    message=f"Stale increment operation (timestamp: {timestamp}, current: {current_timestamp})"
                )

    def SyncDecrement(self, request, context):
        """
        Handle a synchronization decrement request from another replica.
        
        Args:
            request: SyncDecrementRequest with book title, amount, fail flag and timestamp
            context: gRPC context
            
        Returns:
            SyncWriteResponse indicating success or failure
        """
        title = request.title
        amount = request.amount
        fail_if_insufficient = request.fail_if_insufficient
        timestamp = request.timestamp
        
        logger.info(f"[{self.replica_id}] 🔄 Sync decrement request from another replica for book: {title}")
        
        with self.lock:
            current_timestamp = self.write_timestamps.get(title, 0)
            
            # Apply write if it has a newer or equal timestamp
            if timestamp >= current_timestamp:
                current_stock = self.data.get(title, 0)
                new_stock = current_stock - amount
                
                if new_stock < 0 and fail_if_insufficient:
                    return books_database_pb2.SyncWriteResponse(
                        success=False,
                        message=f"Insufficient stock: {current_stock} < {amount}"
                    )
                    
                self.data[title] = new_stock
                self.write_timestamps[title] = timestamp
                return books_database_pb2.SyncWriteResponse(
                    success=True,
                    message="Sync decrement applied successfully"
                )
            else:
                return books_database_pb2.SyncWriteResponse(
                    success=False,
                    message=f"Stale decrement operation (timestamp: {timestamp}, current: {current_timestamp})"
                )

    def SyncCompareAndSwap(self, request, context):
        """
        Handle a synchronization compare-and-swap request from another replica.
        
        Args:
            request: SyncCompareAndSwapRequest with book title, expected stock, new stock, and timestamp
            context: gRPC context
            
        Returns:
            SyncWriteResponse indicating success or failure
        """
        title = request.title
        expected_stock = request.expected_stock
        new_stock = request.new_stock
        timestamp = request.timestamp
        
        logger.info(f"[{self.replica_id}] 🔄 Sync CAS request from another replica for book: {title}")
        
        with self.lock:
            current_timestamp = self.write_timestamps.get(title, 0)
            
            # Apply write if it has a newer or equal timestamp
            if timestamp >= current_timestamp:
                current_stock = self.data.get(title, 0)
                
                # For CAS sync, we trust the initiating replica's decision
                # If they decided the CAS should succeed, we apply it directly
                self.data[title] = new_stock
                self.write_timestamps[title] = timestamp
                
                return books_database_pb2.SyncWriteResponse(
                    success=True,
                    message="Sync CAS applied successfully"
                )
            else:
                return books_database_pb2.SyncWriteResponse(
                    success=False,
                    message=f"Stale CAS operation (timestamp: {timestamp}, current: {current_timestamp})"
                )

def serve():
    """Start the gRPC server"""
    # Get environment variables
    replica_id = os.environ.get("REPLICA_ID", "books_db1")
    known_replicas_str = os.environ.get("KNOWN_REPLICAS", "books_db1,books_db2,books_db3")
    known_replicas = known_replicas_str.split(",")
    
    # Create server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    service = ChainReplicationReplica(replica_id, known_replicas)
    
    # Add services to the server
    books_database_pb2_grpc.add_BooksDatabaseServicer_to_server(service, server)
    books_database_pb2_grpc.add_ReplicaSyncServicer_to_server(service, server)
    
    # Start server
    server.add_insecure_port("[::]:50056")
    server.start()
    logger.info(f"[{replica_id}] 🚀 Books Database Chain Replica started on port 50056")
    
    # Keep server running
    server.wait_for_termination()


if __name__ == "__main__":
    # Add a small random delay to prevent all replicas starting exactly simultaneously
    time.sleep(random.uniform(0.1, 2.0))
    serve()
