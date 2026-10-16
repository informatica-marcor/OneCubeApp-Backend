def calculate_due_recurring_scheduled_for(schedule, today):
    if not schedule.scheduled_at:
        return None

    interval_days = schedule.recurrence_interval or 1

    if interval_days <= 0:
        return None

    start_date = schedule.scheduled_at

    # Todavía no llega la primera fecha de envío.
    if today < start_date:
        return None

    elapsed_days = (today - start_date).days

    occurrence_index = elapsed_days // interval_days

    scheduled_for = start_date + timedelta(
        days=occurrence_index * interval_days
    )

    return scheduled_for