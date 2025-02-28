import sys
import os
import random

# This set of lines are needed to import the gRPC stubs.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))

from fraud_detection import fraud_detection_pb2 as fraud_detection
from fraud_detection import fraud_detection_pb2_grpc as fraud_detection_grpc

import grpc
from concurrent import futures

# Create a class to define the server functions
class FraudDetectionService(fraud_detection_grpc.FraudDetectionServicer):
    def CheckFraud(self, request, context):
        # Dummy logic for fraud detection: flagging orders above a certain amount as fraud
        is_fraudulent = request.amount > 1000 or random.choice([True, False])
        
        response = fraud_detection.FraudCheckResponse()
        response.is_fraudulent = is_fraudulent
        response.message = "Fraud detected" if is_fraudulent else "Transaction is legitimate"
        
        print(f"Checked order {request.order_id}: {response.message}")
        return response

def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    fraud_detection_grpc.add_FraudDetectionServicer_to_server(FraudDetectionService(), server)
    
    port = "50051"
    server.add_insecure_port("[::]:" + port)
    server.start()
    print(f"Fraud detection service started. Listening on port {port}.")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
