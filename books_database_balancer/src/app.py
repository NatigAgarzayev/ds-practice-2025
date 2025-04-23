import os
import sys
import time
import threading
import grpc
import logging
from concurrent import futures
import random

# Fix import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from utils.pb.books_database import books_database_pb2_grpc, books_database_pb2

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("books_db_balancer")

class ChainReplicationBalancer(books_database_pb2_grpc.BooksDatabaseServicer):
    def __init__(self, replica_addresses):
        """
        Initialize the chain replication balancer.
        
        Args:
            replica_addresses: List of replica host:port addresses
        """
        self.replica_addresses = replica_addresses
        self.replica_stubs = {}
        self.lock = threading.RLock()
        self.healthy_replicas = []
        
        # Chain replication specific state
        self.head_replica = None  # The head of the chain for writes
        self.tail_replica = None  # The tail of the chain for consistent reads
        
        # Connect to all replicas
        self._connect_to_replicas()
        
        # Start health check thread
        threading.Thread(target=self._health_check_loop, daemon=True).start()
        
        logger.info(f"🔄 Chain Replication Balancer initialized with {len(replica_addresses)} replicas")
    
    def _connect_to_replicas(self):
        """Connect to all database replicas"""
        for address in self.replica_addresses:
            try:
                channel = grpc.insecure_channel(address)
                stub = books_database_pb2_grpc.BooksDatabaseStub(channel)
                
                # Test connection with a read request
                try:
                    stub.Read(books_database_pb2.ReadRequest(title="test_connection"))
                    with self.lock:
                        self.replica_stubs[address] = stub
                        if address not in self.healthy_replicas:
                            self.healthy_replicas.append(address)
                    logger.info(f"✅ Connected to replica at {address}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to test connection to {address}: {str(e)}")
            except Exception as e:
                logger.error(f"❌ Failed to create channel to {address}: {str(e)}")
        
        # Determine head and tail based on sorted list of healthy replicas
        self._determine_chain_endpoints()
    
    def _determine_chain_endpoints(self):
        """Determine the head and tail of the chain based on sorted replica IDs"""
        with self.lock:
            if not self.healthy_replicas:
                self.head_replica = None
                self.tail_replica = None
                return
            
            # Sort replicas to maintain consistent chain order
            sorted_replicas = sorted(self.healthy_replicas)
            
            # Head is first in sorted order
            self.head_replica = sorted_replicas[0]
            
            # Tail is last in sorted order
            self.tail_replica = sorted_replicas[-1]
            
            logger.info(f"Chain endpoints: HEAD={self.head_replica}, TAIL={self.tail_replica}")
    
    def _health_check_loop(self):
        """Periodically check health of all replicas and update chain endpoints"""
        while True:
            logger.debug("🔍 Performing health check on replicas")
            for address in self.replica_addresses:
                try:
                    channel = grpc.insecure_channel(address)
                    stub = books_database_pb2_grpc.ReplicaSyncStub(channel)
                    response = stub.GetStatus(books_database_pb2.StatusRequest())
                    
                    if response.is_alive:
                        with self.lock:
                            if address not in self.replica_stubs:
                                self.replica_stubs[address] = books_database_pb2_grpc.BooksDatabaseStub(channel)
                            if address not in self.healthy_replicas:
                                self.healthy_replicas.append(address)
                                logger.info(f"✅ Replica {address} is now healthy")
                                # Recalculate chain endpoints if replicas change
                                self._determine_chain_endpoints()
                    else:
                        with self.lock:
                            if address in self.healthy_replicas:
                                self.healthy_replicas.remove(address)
                                logger.warning(f"⚠️ Replica {address} reported not alive")
                                # Recalculate chain endpoints if replicas change
                                self._determine_chain_endpoints()
                except Exception:
                    with self.lock:
                        if address in self.healthy_replicas:
                            self.healthy_replicas.remove(address)
                            logger.warning(f"⚠️ Replica {address} is unhealthy")
                            # Recalculate chain endpoints if replicas change
                            self._determine_chain_endpoints()
            
            # Sleep for 5 seconds before next check
            time.sleep(5)
    
    def Read(self, request, context):
        """
        Handle read requests by forwarding to the tail for linearizable reads.
        
        Args:
            request: ReadRequest
            context: gRPC context
        
        Returns:
            ReadResponse from the tail replica
        """
        logger.info(f"📖 Load balancer: Read request for book: {request.title}")
        
        with self.lock:
            # For linearizable reads, direct to tail
            if self.tail_replica and self.tail_replica in self.replica_stubs:
                tail_stub = self.replica_stubs[self.tail_replica]
                try:
                    return tail_stub.Read(request)
                except Exception as e:
                    logger.error(f"❌ Error reading from tail {self.tail_replica}: {str(e)}")
            
            # If tail is unavailable, fall back to any healthy replica
            # (this sacrifices linearizability but preserves availability)
            if self.healthy_replicas:
                fallback_replica = random.choice(self.healthy_replicas)
                logger.warning(f"⚠️ Falling back to replica {fallback_replica} for read (may not be linearizable)")
                try:
                    return self.replica_stubs[fallback_replica].Read(request)
                except Exception as e:
                    logger.error(f"❌ Error during fallback read from {fallback_replica}: {str(e)}")
            
            # No healthy replicas available
            return books_database_pb2.ReadResponse(
                stock=0,
                success=False,
                message="No healthy database replicas available"
            )
    
    def Write(self, request, context):
        """
        Handle write requests by forwarding to the head of the chain.
        
        Args:
            request: WriteRequest
            context: gRPC context
        
        Returns:
            WriteResponse after chain replication completes
        """
        logger.info(f"✏️ Load balancer: Write request for book: {request.title}")
        
        with self.lock:
            # For writes, direct to head of chain
            if self.head_replica and self.head_replica in self.replica_stubs:
                head_stub = self.replica_stubs[self.head_replica]
                try:
                    return head_stub.Write(request)
                except Exception as e:
                    logger.error(f"❌ Error writing to head {self.head_replica}: {str(e)}")
            
            # No head available
            return books_database_pb2.WriteResponse(
                success=False,
                message="No healthy head replica available for write operation"
            )

def serve():
    """Start the load balancer gRPC server"""
    # Get environment variables
    replica_addresses_str = os.environ.get("REPLICA_ADDRESSES", "books_db1:50056,books_db2:50056,books_db3:50056")
    replica_addresses = replica_addresses_str.split(",")
    
    # Create server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    balancer = ChainReplicationBalancer(replica_addresses)
    books_database_pb2_grpc.add_BooksDatabaseServicer_to_server(balancer, server)
    
    # Start server
    server.add_insecure_port("[::]:50056")
    server.start()
    logger.info("🚀 Chain Replication Books Database Balancer started on port 50056")
    
    # Keep server running
    server.wait_for_termination()


if __name__ == "__main__":
    # Small delay to ensure database replicas are started
    time.sleep(3)
    serve()
