"""
Tests for app/event_bus.py

TDD: these tests are written BEFORE implementation and must initially FAIL
with ModuleNotFoundError: No module named 'app.event_bus'.

Covers:
- subscribe() + publish() invokes handler
- multiple subscribers (fan-out)
- handler exception doesn't break other handlers
- publish to topic with no subscribers is a no-op
- payload dataclass is passed correctly to handler
- InProcessEventBus is the default module-level singleton
- all topic constants are importable strings
- subscribing same handler twice calls it twice
- different topics are isolated
"""
import asyncio
import pytest


class TestInProcessEventBus:

    @pytest.mark.asyncio
    async def test_subscribe_and_publish_calls_handler(self):
        """Happy path: subscribed handler is called after publish."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        received = []

        async def handler(payload):
            received.append(payload)

        bus.subscribe("test.topic", handler)
        await bus.publish("test.topic", "hello")
        await asyncio.sleep(0)  # yield to let create_task run

        assert received == ["hello"]

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_called(self):
        """Happy path: all subscribers for a topic are called (fan-out)."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        calls = []

        async def h1(p): calls.append(("h1", p))
        async def h2(p): calls.append(("h2", p))

        bus.subscribe("x", h1)
        bus.subscribe("x", h2)
        await bus.publish("x", 42)
        await asyncio.sleep(0)

        assert ("h1", 42) in calls
        assert ("h2", 42) in calls

    @pytest.mark.asyncio
    async def test_handler_exception_isolated(self):
        """Failure: exception in one handler does not prevent other handlers from running."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        second_called = []

        async def bad_handler(p):
            raise RuntimeError("boom")

        async def good_handler(p):
            second_called.append(p)

        bus.subscribe("boom", bad_handler)
        bus.subscribe("boom", good_handler)
        await bus.publish("boom", "payload")
        await asyncio.sleep(0.01)  # allow both tasks to run

        assert second_called == ["payload"]

    @pytest.mark.asyncio
    async def test_unknown_topic_no_error(self):
        """Edge case: publishing to topic with no subscribers is a no-op."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        # Should not raise
        await bus.publish("nonexistent.topic", {"data": 1})

    @pytest.mark.asyncio
    async def test_payload_dataclass_passed_correctly(self):
        """Happy path: OrderFilledPayload dataclass fields are preserved through publish."""
        from app.event_bus import InProcessEventBus, OrderFilledPayload, ORDER_FILLED
        bus = InProcessEventBus()
        received = []

        async def handler(payload):
            received.append(payload)

        bus.subscribe(ORDER_FILLED, handler)
        payload = OrderFilledPayload(
            position_id=7, user_id=1, product_id="BTC-USD",
            fill_type="base_order", quote_amount=100.0,
            base_amount=0.001, price=100_000.0,
        )
        await bus.publish(ORDER_FILLED, payload)
        await asyncio.sleep(0)

        assert len(received) == 1
        assert received[0].position_id == 7
        assert received[0].product_id == "BTC-USD"
        assert received[0].fill_type == "base_order"
        assert received[0].is_paper_trading is False

    def test_module_singleton_exists(self):
        """Happy path: module-level event_bus singleton is InProcessEventBus."""
        from app.event_bus import event_bus, InProcessEventBus
        assert isinstance(event_bus, InProcessEventBus)

    @pytest.mark.asyncio
    async def test_topic_constants_defined(self):
        """Happy path: all topic constants are importable strings."""
        from app.event_bus import (
            ORDER_FILLED, POSITION_OPENED, POSITION_CLOSED,
            BOT_STARTED, BOT_STOPPED,
        )
        for const in [ORDER_FILLED, POSITION_OPENED, POSITION_CLOSED, BOT_STARTED, BOT_STOPPED]:
            assert isinstance(const, str)
            assert "." in const  # namespaced topic

    @pytest.mark.asyncio
    async def test_subscribe_same_handler_twice_both_called(self):
        """Edge case: subscribing same handler twice calls it twice per publish."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        count = []

        async def handler(p): count.append(1)

        bus.subscribe("t", handler)
        bus.subscribe("t", handler)
        await bus.publish("t", None)
        await asyncio.sleep(0)

        assert len(count) == 2

    @pytest.mark.asyncio
    async def test_different_topics_isolated(self):
        """Edge case: subscribing to topic A does not receive topic B events."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        received = []

        async def handler(p): received.append(p)

        bus.subscribe("topic.a", handler)
        await bus.publish("topic.b", "should not arrive")
        await asyncio.sleep(0)

        assert received == []

    @pytest.mark.asyncio
    async def test_all_payload_dataclasses_importable(self):
        """Happy path: all payload dataclasses are importable and instantiable."""
        from app.event_bus import (
            OrderFilledPayload, BotStartedPayload, BotStoppedPayload,
        )
        # Instantiate each to verify required fields
        o = OrderFilledPayload(
            position_id=1, user_id=1, product_id="ETH-USD",
            fill_type="sell_order", quote_amount=50.0,
            base_amount=0.1, price=500.0,
        )
        assert o.profit is None
        assert o.is_paper_trading is False

        b_start = BotStartedPayload(bot_id=3, user_id=1)
        b_stop = BotStoppedPayload(bot_id=3, user_id=1)
        assert b_start.bot_id == 3
        assert b_stop.bot_id == 3
