import sys
import os
import random

# Ensure utils/pb is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))

from suggestions import suggestions_pb2 as suggestions
from suggestions import suggestions_pb2_grpc as suggestions_grpc

import grpc
from concurrent import futures

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
    "The Hobbit by J.R.R. Tolkien"
]

# Create a class to define the server functions
class SuggestionsService(suggestions_grpc.SuggestionsServicer):
    def GetBookSuggestions(self, request, context):
        num_suggestions = min(request.num_suggestions, len(BOOKS))
        suggested_books = random.sample(BOOKS, num_suggestions)
        
        response = suggestions.SuggestionsResponse()
        response.books.extend(suggested_books)
        
        print(f"Generated {num_suggestions} book suggestions for user {request.user_id}.")
        return response

def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    suggestions_grpc.add_SuggestionsServicer_to_server(SuggestionsService(), server)
    
    port = "50053"
    server.add_insecure_port("[::]:" + port)
    server.start()
    print(f"Suggestions service started. Listening on port {port}.")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()