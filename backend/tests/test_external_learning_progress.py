from copy import deepcopy
from uuid import uuid4
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.learning_progress import apply_learning_change
from app.api.routes.repertoire import LearningChange, _partition_sort_key


def change(state, action="CORRECT", **kwargs):
    return apply_learning_change(state, action=action, product_id=kwargs.pop("product_id", None),
        piece_id=kwargs.pop("piece_id", None), statuses=None, catalog={"school": ["piece"]},
        session_id="lesson", **kwargs)


def test_external_followup_is_private_preserves_catalog_and_can_complete():
    before = {"product_id": "school", "books": {"school": {"pieces": {}, "completed": False, "current_piece_id": "piece"}}}
    original = deepcopy(before)
    result = change(before, external_title="  Imagine  ", external_composer=" Lennon ")
    key = result["product_id"]
    assert before == original
    assert result["books"]["school"] == before["books"]["school"]
    assert result["books"][key]["title"] == "Imagine"
    assert result["books"][key]["composer"] == "Lennon"
    assert change(result, "CONTINUE") == result
    completed = change(change(result, "COMPLETE_PIECE"), "COMPLETE_BOOK")
    following = change(completed, "NEXT_BOOK", external_title="Autre morceau")
    assert following["product_id"] != key
    assert following["books"][key]["completed"]
    assert following["books"][key]["pieces"][key]["status"] == "COMPLETED"
    back = change(following, product_id="school", piece_id="piece")
    assert back["books"][key]["title"] == "Imagine"


def test_rename_keeps_same_entry():
    state = change({"product_id": None, "books": {}}, external_title="Titre initial")
    key = state["product_id"]
    result = change(state, product_id=key, external_title="Titre corrigé")
    assert list(result["books"]) == [key]
    assert result["books"][key]["title"] == "Titre corrigé"


@pytest.mark.parametrize("kwargs", [{"external_title": "   "}, {"external_title": "x" * 256},
    {"product_id": "school", "external_title": "Ne pas modifier le catalogue"},
    {"product_id": str(uuid4()), "external_title": "Identifiant étranger"}])
def test_invalid_external_input_is_rejected(kwargs):
    with pytest.raises(HTTPException):
        change({"product_id": None, "books": {}}, **kwargs)


def test_request_accepts_optional_external_fields():
    payload = LearningChange(revision=0, session_id=uuid4(), action="CORRECT", external_title="Imagine", external_composer="Lennon")
    assert payload.product_id is None
    assert payload.external_title == "Imagine"


def test_school_degrees_are_sorted_numerically_before_other_partitions():
    titles = ["Partitions Ados", "Partition degré 11", "Partition degré 2 - Mon 1er Piano",
              "Partition degré 10", "Partition classe concours", "Partition degré 1", "Partition degré 3"]
    sorted_titles = [p.title for p in sorted([SimpleNamespace(title=t) for t in titles], key=_partition_sort_key)]
    assert sorted_titles == ["Partition degré 1", "Partition degré 2 - Mon 1er Piano", "Partition degré 3",
                             "Partition degré 10", "Partition degré 11", "Partition classe concours", "Partitions Ados"]
