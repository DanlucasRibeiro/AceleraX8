import time


class AntiDuplicate:

    def __init__(self, cooldown=2.0):
        self.last_side = {}
        self.last_pass = {}
        self.last_inside_zone = {}
        self.last_zone_state = {}

        self.cooldown = cooldown

    def process(self, car_id, y, finish_line):
        now = time.time()

        current_side = y > finish_line

        if car_id not in self.last_side:
            self.last_side[car_id] = current_side
            return False

        previous_side = self.last_side[car_id]
        crossed = previous_side != current_side

        if crossed:
            if car_id in self.last_pass:
                elapsed = now - self.last_pass[car_id]

                if elapsed < self.cooldown:
                    self.last_side[car_id] = current_side
                    return False

            self.last_pass[car_id] = now
            self.last_side[car_id] = current_side
            return True

        self.last_side[car_id] = current_side
        return False

    def process_zone(self, car_id, x, y, zone):
        now = time.time()

        x1, y1, x2, y2 = zone
        inside_x = x1 <= x <= x2

        if y < y1:
            current_state = "above"
        elif y > y2:
            current_state = "below"
        else:
            current_state = "inside"

        inside_zone = inside_x and current_state == "inside"

        if car_id not in self.last_zone_state:
            self.last_zone_state[car_id] = current_state
            self.last_inside_zone[car_id] = inside_zone
            return False

        previous_state = self.last_zone_state[car_id]
        was_inside = self.last_inside_zone[car_id]
        entered_zone = inside_zone and not was_inside
        jumped_over_zone = {previous_state, current_state} == {"above", "below"}

        if entered_zone or jumped_over_zone:
            elapsed = now - self.last_pass.get(car_id, 0)

            if elapsed >= self.cooldown:
                self.last_pass[car_id] = now
                self.last_zone_state[car_id] = current_state
                self.last_inside_zone[car_id] = inside_zone
                return True

        self.last_zone_state[car_id] = current_state
        self.last_inside_zone[car_id] = inside_zone
        return False
