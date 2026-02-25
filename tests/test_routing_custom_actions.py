"""
Tests for custom action routing behavior.
"""

import pytest

from core.routing import Router, _iter_sorted_custom_actions
from core.views import ViewSet, action


class TestCustomActionOrdering:
    def test_static_paths_are_registered_before_dynamic_paths(self):
        class StrategyViewSet(ViewSet):
            _exclude_crud = True

            @action(methods=["GET"], detail=False, url_path="{name}")
            async def a_dynamic(self, request, db, name: str):
                return {"name": name}

            @action(methods=["GET"], detail=False, url_path="list")
            async def z_list(self, request, db):
                return {"ok": True}

        actions = _iter_sorted_custom_actions(StrategyViewSet, detail_filter=False)
        names = [name for name, _ in actions]
        assert names.index("z_list") < names.index("a_dynamic")

    def test_custom_sorter_can_override_default_order(self):
        class CustomViewSet(ViewSet):
            _exclude_crud = True
            custom_action_sort_key = staticmethod(
                lambda action_name, url_path, detail: (0 if action_name == "a_dynamic" else 1, action_name)
            )

            @action(methods=["GET"], detail=False, url_path="{name}")
            async def a_dynamic(self, request, db, name: str):
                return {"name": name}

            @action(methods=["GET"], detail=False, url_path="list")
            async def z_list(self, request, db):
                return {"ok": True}

        actions = _iter_sorted_custom_actions(CustomViewSet, detail_filter=False)
        names = [name for name, _ in actions]
        assert names[0] == "a_dynamic"


class TestCustomActionConflictPolicy:
    def test_route_conflict_policy_raise_throws_error(self):
        class ConflictViewSet(ViewSet):
            _exclude_crud = True
            route_conflict_policy = "raise"

            @action(methods=["GET"], detail=False, url_path="same")
            async def first(self, request, db):
                return {"first": True}

            @action(methods=["GET"], detail=False, url_path="same")
            async def second(self, request, db):
                return {"second": True}

        router = Router()
        with pytest.raises(ValueError, match="Duplicate custom action route detected"):
            router.register_viewset("/conflicts", ConflictViewSet, basename="conflict")
