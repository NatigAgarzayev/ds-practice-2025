import sys
import os
import grpc
import time
import random
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor

# Fix import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from utils.pb.books_database import books_database_pb2_grpc, books_database_pb2

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("db_test_client")

class DatabaseTestClient:
    def __init__(self, server_address, test_type='sequential'):
        self.server_address = server_address
        self.channel = grpc.insecure_channel(server_address)
        self.stub = books_database_pb2_grpc.BooksDatabaseStub(self.channel)
        self.test_type = test_type
    
    def read_book(self, title):
        """Read a book's stock"""
        try:
            response = self.stub.Read(books_database_pb2.ReadRequest(title=title))
            if response.success:
                logger.info(f"Book '{title}' has {response.stock} copies in stock")
            else:
                logger.warning(f"Book '{title}' not found: {response.message}")
            return response
        except Exception as e:
            logger.error(f"Error reading book '{title}': {str(e)}")
            return None
    
    def write_book(self, title, new_stock):
        """Update a book's stock"""
        try:
            response = self.stub.Write(
                books_database_pb2.WriteRequest(title=title, new_stock=new_stock)
            )
            if response.success:
                logger.info(f"Updated stock for '{title}' to {new_stock}: {response.message}")
            else:
                logger.warning(f"Failed to update stock for '{title}': {response.message}")
            return response
        except Exception as e:
            logger.error(f"Error updating book '{title}': {str(e)}")
            return None
    
    def run_sequential_test(self, iterations=5):
        """Run sequential read/write operations"""
        logger.info(f"Starting sequential test with {iterations} iterations")
        test_book = "Test Book " + str(random.randint(1, 1000))
        
        # Initial write
        self.write_book(test_book, 10)
        
        for i in range(iterations):
            # Read current stock
            response = self.read_book(test_book)
            if response and response.success:
                current_stock = response.stock
                # Update stock (decrement by 1)
                self.write_book(test_book, current_stock - 1)
            time.sleep(0.5)  # Small delay between operations
        
        # Final read to verify
        final_response = self.read_book(test_book)
        if final_response and final_response.success:
            logger.info(f"Final stock for '{test_book}': {final_response.stock}")
    
    def run_concurrent_test(self, num_threads=5, operations_per_thread=3):
        """Run concurrent read/write operations to test consistency"""
        logger.info(f"Starting concurrent test with {num_threads} threads")
        test_book = "Concurrent Test Book " + str(random.randint(1, 1000))
        
        # Initial write
        self.write_book(test_book, 20)
        
        def worker(worker_id):
            for i in range(operations_per_thread):
                # Read and then write
                response = self.read_book(test_book) 
                if response and response.success:
                    # Small random delay to simulate processing
                    time.sleep(random.uniform(0.1, 0.5))
                    # Decrement the stock
                    self.write_book(test_book, response.stock - 1)
        
        # Create and start threads
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            # Wait for all to complete
            for future in futures:
                future.result()
                
        # Final read to verify consistency
        time.sleep(2)  # Allow all replicas to sync
        final_response = self.read_book(test_book)
        if final_response and final_response.success:
            expected_stock = 20 - (num_threads * operations_per_thread)
            logger.info(f"Final stock for '{test_book}': {final_response.stock}")
            logger.info(f"Expected stock: {expected_stock}")
            if final_response.stock == expected_stock:
                logger.info("✅ Test passed! Consistency maintained.")
            else:
                logger.warning("⚠️ Test failed! Inconsistency detected.")
    
    def run_test(self):
        """Run the selected test type"""
        if self.test_type == 'sequential':
            self.run_sequential_test()
        elif self.test_type == 'concurrent':
            self.run_concurrent_test()
        else:
            logger.error(f"Unknown test type: {self.test_type}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the distributed database")
    parser.add_argument("--server", default="localhost:50056", help="Server address")
    parser.add_argument("--test", default="sequential", choices=["sequential", "concurrent"],
                        help="Test type (sequential or concurrent)")
    args = parser.parse_args()
    
    client = DatabaseTestClient(args.server, args.test)
    client.run_test()
