from datetime import datetime, timedelta

# Generate 15-min slots between 09:00 and 21:00
def generate_time_slots():
    slots = []
    start_time = datetime.strptime("09:00", "%H:%M")
    end_time = datetime.strptime("21:00", "%H:%M")
    current_time = start_time

    while current_time <= end_time:
        slots.append(current_time.strftime("%I:%M %p"))  # 12-hour format
        current_time += timedelta(minutes=15)
    return slots


# Generate available dates starting from today (next 30 days for example)
def generate_available_dates(days_ahead=30):
    today = datetime.today().date()
    return [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_ahead)]


# Filter out already booked slots
def filter_booked_slots(all_slots, booked_slots):
    return [slot for slot in all_slots if slot not in booked_slots]




