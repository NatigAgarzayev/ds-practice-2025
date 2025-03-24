class VectorClock:
    def __init__(self, services):
        self.clock = {service: 0 for service in services}

    def increment(self, service):
        self.clock[service] += 1

    def merge(self, other):
        for key in self.clock:
            self.clock[key] = max(self.clock[key], other.get(key, 0))

    def to_dict(self):
        return self.clock

    def from_dict(self, d):
        self.clock = d

    def __str__(self):
        return str(self.clock)