from datetime import date

from copilot.guard import DailyBudget, RateLimiter, client_ip


def test_rate_limit_per_visitor_and_window():
    t = [0.0]
    rl = RateLimiter(2, window=60, clock=lambda: t[0])
    assert rl.allow("a") and rl.allow("a") and not rl.allow("a")
    assert rl.allow("b")                                   # another visitor is unaffected
    t[0] = 61
    assert rl.allow("a")                                   # window has passed


def test_daily_budget_resets_next_day():
    day = [date(2026, 9, 29)]
    b = DailyBudget(1, today=lambda: day[0])
    assert b.try_spend() and not b.try_spend()
    day[0] = date(2026, 9, 30)
    assert b.try_spend()


def test_client_ip_prefers_forwarded_for():
    assert client_ip({"x-forwarded-for": "1.2.3.4, 10.0.0.1"}, "10.0.0.1") == "1.2.3.4"
    assert client_ip({}, "5.6.7.8") == "5.6.7.8"
