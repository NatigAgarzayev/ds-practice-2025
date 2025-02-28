import sys
import os
import grpc
import json
import threading

from flask import Flask, request
from flask_cors import CORS

# Ensure utils/pb is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../utils/pb")))

import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc
import suggestions_pb2 as suggestions
import suggestions_pb2_grpc as suggestions_grpc

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

def check_fraud(order_id, amount, result):
    with grpc.insecure_channel('fraud_detection:50051') as channel:
        stub = fraud_detection_grpc.FraudDetectionStub(channel)
        response = stub.CheckFraud(fraud_detection.FraudCheckRequest(order_id=order_id, amount=amount))
        result['fraud'] = response.is_fraudulent

def verify_transaction(order_id, user_id, items, credit_card, result):
    with grpc.insecure_channel('transaction_verification:50052') as channel:
        stub = transaction_verification_grpc.TransactionVerificationStub(channel)
        response = stub.VerifyTransaction(transaction_verification.TransactionVerificationRequest(
            transaction_id=order_id, user_id=user_id, items=items, credit_card=credit_card))
        result['valid_transaction'] = response.is_valid

def get_suggestions(user_id, num_suggestions, result):
    with grpc.insecure_channel('suggestions:50053') as channel:
        stub = suggestions_grpc.SuggestionsStub(channel)
        response = stub.GetBookSuggestions(suggestions.SuggestionsRequest(user_id=user_id, num_suggestions=num_suggestions))
        result['suggested_books'] = [{'title': book} for book in response.books]

@app.route('/checkout', methods=['POST'])
def checkout():
    request_data = json.loads(request.data)
    order_id = request_data.get('orderId', 'unknown')
    amount = request_data.get('amount', 0)
    user_id = request_data.get('userId', 'unknown')
    items = request_data.get('items', [])
    credit_card = request_data.get('creditCard', '')
    
    result = {}
    threads = []
    
    threads.append(threading.Thread(target=check_fraud, args=(order_id, amount, result)))
    threads.append(threading.Thread(target=verify_transaction, args=(order_id, user_id, items, credit_card, result)))
    threads.append(threading.Thread(target=get_suggestions, args=(user_id, 3, result)))
    
    for thread in threads:
        thread.start()
    
    for thread in threads:
        thread.join()
    
    status = "Order Approved" if result.get('valid_transaction', False) and not result.get('fraud', True) else "Order Rejected"
    
    response = {
        'orderId': order_id,
        'status': status,
        'suggestedBooks': result.get('suggested_books', [])
    }
    
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
