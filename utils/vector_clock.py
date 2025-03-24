class VectorClock:
    def __init__(self, services):
        self.clock = {service: 0 for service in services}

    def increment(self, service):
        self.clock[service] += 1

    def update(self, other_clock):
        for key in self.clock:
            self.clock[key] = max(self.clock[key], other_clock.get(key, 0))

    def to_dict(self):
        return self.clock

    def from_dict(self, clock_dict):
        self.clock = clock_dict

    def has_happened_before(self, other_clock):
        for k in self.clock:
            if self.clock[k] > other_clock.get(k, 0):
                return False
        return True
