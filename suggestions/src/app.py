import sys
import os
import random
# Ensure utils/pb is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))

from suggestions import suggestions_pb2 as suggestions
from suggestions import suggestions_pb2_grpc as suggestions_grpc

import grpc
from concurrent import futures
import logging

# Configure logging
logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    level=logging.INFO  # Change to DEBUG for more details
)

logger = logging.getLogger(__name__)

# Static list of books for suggestions
BOOKS = [
    "1984 by George Orwell",
    "To Kill a Mockingbird by Harper Lee",
    "The Great Gatsby by F. Scott Fitzgerald",
    "Moby Dick by Herman Melville",
    "Pride and Prejudice by Jane Austen",
    "War and Peace by Leo Tolstoy",
    "The Catcher in the Rye by J.D. Salinger",
    "Brave New World by Aldous Huxley",
    "Ulysses by James Joyce",
    "The Hobbit by J.R.R. Tolkien",
    "DEAD MAXIM by Natig"
]

# Create a class to define the server functions
class SuggestionsService(suggestions_grpc.SuggestionsServicer):
    def GetBookSuggestions(self, request, context):
        """Fetches book suggestions for a given user."""
        logger.info(f"Received book suggestion request for User ID: {request.user_id} - Requesting {request.num_suggestions} books.")

        num_suggestions = min(request.num_suggestions, len(BOOKS))
        suggested_books = random.sample(BOOKS, num_suggestions)

        response = suggestions.SuggestionsResponse()
        response.books.extend(suggested_books)

        logger.info(f"Suggested books for User ID {request.user_id}: {suggested_books}")
        return response

def serve():
    logger.info("Starting Book Suggestions gRPC service...")

    server = grpc.server(futures.ThreadPoolExecutor())
    suggestions_grpc.add_SuggestionsServicer_to_server(SuggestionsService(), server)
    
    port = "50053"
    server.add_insecure_port("[::]:" + port)
    server.start()
    logger.info(f"Suggestions service started. Listening on port {port}.")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()