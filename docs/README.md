# Documentation

This folder should contain your documentation, explaining the structure and content of your project. It should also contain your diagrams, explaining the architecture. The recommended writing format is Markdown.

## Structure
It is microservices based python flask web application where you can order books. We use docker compose to launch the web application.
We have 3 microservices. They are Fraud Detection system, Transaction Verification system, Suggestions system. All these 3 services are ran by a orchestrator which contains the main general interaction logic between microservices and also responsible for the chekout process.
We used proto schemas for estbalishing DB prototype.    

We have added 2 more services: executor and order_queue. We have implemented vectors clocks, queue, executors and leader elections.
Now it prioritize premium users over non-premium users. 

## Installation
In order to launch launch your docker desktop, then move to the project directory:
```sh
cd ./ds-practice-2025
```
a path may be varied.

```sh
docker compose build
```

Then,

```sh
docker compose up
```

Finally, open on the browser,

```
[localhost:8082](http://localhost:8082/)
```

## Folder structure
.
├── .gitignore
├── docker-compose.yaml
├── README.md
│
├── docs/
│   ├── README.md
│   ├── architecture_diagram.png
│   ├── folder_structure.txt
│   └── system_diagram.png
│
├── executor/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       └── app.py
│
├── fraud_detection/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       └── app.py
│
├── frontend/
│   ├── Dockerfile
│   └── src/
│       └── index.html
│
├── orchestrator/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       └── app.py
│
├── order_queue/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       └── app.py
│
├── suggestions/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       └── app.py
│
├── transaction_verification/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       └── app.py
│
└── utils/
    ├── README.md
    ├── vector_clock.py
    ├── api/
    │   ├── bookstore.yaml
    │   ├── fintech.yaml
    │   └── ridehailing.yaml
    ├── other/
    │   └── hotreload.py
    └── pb/
        ├── __init__.py
        ├── executor/
        │   ├── executor.proto
        │   ├── executor_pb2.py
        │   ├── executor_pb2.pyi
        │   ├── executor_pb2_grpc.py
        │   └── __pycache__/
        ├── fraud_detection/
        │   ├── fraud_detection.proto
        │   ├── fraud_detection_pb2.py
        │   ├── fraud_detection_pb2.pyi
        │   ├── fraud_detection_pb2_grpc.py
        │   ├── __init__.py
        │   └── __pycache__/
        ├── order_queue/
        │   ├── order_queue.proto
        │   ├── order_queue_pb2.py
        │   ├── order_queue_pb2.pyi
        │   ├── order_queue_pb2_grpc.py
        │   └── __pycache__/
        ├── suggestions/
        │   ├── suggestions.proto
        │   ├── suggestions_pb2.py
        │   ├── suggestions_pb2.pyi
        │   ├── suggestions_pb2_grpc.py
        │   ├── __init__.py
        │   └── __pycache__/
        └── transaction_verification/
            ├── transaction_verification.proto
            ├── transaction_verification_pb2.py
            ├── transaction_verification_pb2.pyi
            ├── transaction_verification_pb2_grpc.py
            ├── __init__.py
            └── __pycache__/