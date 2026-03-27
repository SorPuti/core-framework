"""
Tests for custom action routing behavior.
"""

import pytest

from strider.routing import Router, _iter_sorted_custom_actions
from strider.views import ViewSet, action


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


class TestViewSetRoutingSignatureHandling:
    def test_build_viewset_call_kwargs_ignores_missing_db_param(self):
        from strider.routing import _build_viewset_call_kwargs

        async def create_without_db(self, request, body):
            return body

        kwargs = _build_viewset_call_kwargs(
            create_without_db,
            request=object(),
            db=object(),
            _user=object(),
            extra_kwargs={"body": {"foo": "bar"}},
        )

        assert "db" not in kwargs
        assert kwargs["body"] == {"foo": "bar"}

    def test_build_viewset_call_kwargs_includes_db_when_accepted(self):
        from strider.routing import _build_viewset_call_kwargs

        async def create_with_db(self, request, db, body):
            return body

        db_obj = object()
        kwargs = _build_viewset_call_kwargs(
            create_with_db,
            request=object(),
            db=db_obj,
            _user=object(),
            extra_kwargs={"body": {"foo": "bar"}},
        )

        assert kwargs["db"] is db_obj
        assert kwargs["body"] == {"foo": "bar"}


class TestPathParamMergeAndCoercion:
    def test_merge_maps_id_to_pk_and_coerces_int(self):
        from strider.routing import _merge_path_params_for_signature

        class _VS:
            lookup_field = "id"
            lookup_url_kwarg = "id"

        async def handler(self, request, db, pk: int):
            return pk

        out = _merge_path_params_for_signature(
            handler, {"id": "42"}, viewset_class=_VS
        )
        assert out == {"pk": 42}

    def test_merge_invalid_int_raises_stride_error(self):
        from strider.exceptions import StridePathParamBindingError
        from strider.routing import _merge_path_params_for_signature

        class _VS:
            lookup_field = "id"
            lookup_url_kwarg = "id"

        async def handler(self, request, db, pk: int):
            return pk

        with pytest.raises(StridePathParamBindingError):
            _merge_path_params_for_signature(handler, {"id": "not-int"}, viewset_class=_VS)

    def test_merge_pk_with_var_kw_maps_id_without_duplicating_id(self):
        from strider.routing import _merge_path_params_for_signature

        class _VS:
            lookup_field = "id"
            lookup_url_kwarg = "id"

        async def handler(self, request, db, file, pk: int, **kwargs):
            return pk

        out = _merge_path_params_for_signature(
            handler, {"id": "7"}, viewset_class=_VS
        )
        assert out == {"pk": 7}
        assert "id" not in out

    def test_merge_var_kw_only_keeps_lookup_segment_for_get_object(self):
        from strider.routing import _merge_path_params_for_signature

        class _VS:
            lookup_field = "id"
            lookup_url_kwarg = "id"

        async def handler(self, request, db, file, **kwargs):
            return kwargs

        out = _merge_path_params_for_signature(
            handler, {"id": "99"}, viewset_class=_VS
        )
        assert out == {"id": "99"}
