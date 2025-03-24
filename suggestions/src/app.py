import os
import sys
import random
import json
import logging
import grpc
from concurrent import futures
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils")))

from suggestions import suggestions_pb2 as suggestions
from suggestions import suggestions_pb2_grpc as suggestions_grpc
from vector_clock import VectorClock

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Static suggestions
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
    "2077 by Natig",
    "DED MAXIM by Natig",
]

# Simulated order state
orders = {}

class SuggestionsService(suggestions_grpc.SuggestionsServicer):
    def ClearOrder(self, request, context):
        order_id = request.order_id
        final_clock = json.loads(request.final_clock)

        if order_id not in orders:
            return suggestions.ClearResponse(
                cleared=False,
                service="suggestions",
                error="Order not found"
            )

        local_clock = orders[order_id]["clock"].to_dict()

        is_safe_to_clear = all(
            local_clock.get(s, 0) <= final_clock.get(s, 0)
            for s in final_clock
        )

        if is_safe_to_clear:
            del orders[order_id]
            logger.info(f"[{order_id}] Cleared successfully (VC ≤ VCf)")
            return suggestions.ClearResponse(
                cleared=True,
                service="suggestions",
                error=""
            )
        else:
            logger.warning(f"[{order_id}] Cannot clear: local VC > VCf")
            return suggestions.ClearResponse(
                cleared=False,
                service="suggestions",
                error="Vector clock conflict — cannot clear safely"
            )

    def GetBookSuggestions(self, request, context):
        order_id = request.user_id  # cheating: using user_id to pass order_id
        if order_id not in orders:
            orders[order_id] = {
                "clock": VectorClock(["orchestrator", "transaction_verification", "fraud_detection", "suggestions"]),
                "done": {}
            }

        state = orders[order_id]

        # Simulate waiting for event (e) to be done
        logger.info(f"[{order_id}] (f) Waiting for fraud check (e) to complete...")
        time.sleep(0.5)  # simulate dependency wait

        clock = state["clock"]
        clock.increment("suggestions")

        suggestions_list = random.sample(BOOKS, min(request.num_suggestions, len(BOOKS)))

        logger.info(f"[{order_id}] (f) Suggesting {len(suggestions_list)} books | clock={clock}")

        return suggestions.SuggestionsResponse(books=suggestions_list)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    suggestions_grpc.add_SuggestionsServicer_to_server(SuggestionsService(), server)
    server.add_insecure_port("[::]:50053")
    logger.info("Suggestions Service running on port 50053")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()