import sys
import os
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))

from transaction_verification import transaction_verification_pb2 as transaction_verification
from transaction_verification import transaction_verification_pb2_grpc as transaction_verification_grpc

import grpc
from concurrent import futures
import logging

# Configure logging
logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    level=logging.INFO  # Change to DEBUG for more details
)

logger = logging.getLogger(__name__)

# Create a class to define the server functions
class TransactionVerificationService(transaction_verification_grpc.TransactionVerificationServicer):
    def VerifyTransaction(self, request, context):
        """Verifies transaction details including items, user ID, and credit card format."""
        logger.info(f"Received transaction verification request for Transaction ID: {request.transaction_id}")

        is_valid = True
        message = "Transaction is valid"
        
        if not request.items:
            is_valid = False
            message = "Transaction must contain at least one item"
        elif not request.user_id:
            is_valid = False
            message = "User ID is required"
        elif not re.match(r'^[0-9]{16}$', request.credit_card):
            is_valid = False
            message = "Invalid credit card format"
        
        response = transaction_verification.TransactionVerificationResponse()
        response.is_valid = is_valid
        response.message = message

        logger.info(f"Transaction verification result for Transaction ID {request.transaction_id}: {message}")
        return response


def serve():
    logger.info("Starting Transaction Verification gRPC service...")

    server = grpc.server(futures.ThreadPoolExecutor())
    transaction_verification_grpc.add_TransactionVerificationServicer_to_server(TransactionVerificationService(), server)
    
    port = "50052"
    server.add_insecure_port("[::]:" + port)
    server.start()
    logger.info(f"Transaction verification service started. Listening on port {port}.")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()