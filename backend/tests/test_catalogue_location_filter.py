from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.api.routes.catalogue import list_locations


class CatalogueLocationFilterTests(unittest.TestCase):
    def test_location_list_can_be_limited_to_course_type_mappings(self) -> None:
        db = SimpleNamespace(
            scalars=MagicMock(return_value=SimpleNamespace(all=lambda: [])),
        )
        course_type_id = uuid4()

        result = list_locations(active=True, course_type_id=course_type_id, db=db)

        statement = db.scalars.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        self.assertEqual(result, [])
        self.assertIn("JOIN planning_course_types", sql)
        self.assertIn("planning_course_types.course_type_id", sql)
        self.assertIn(course_type_id, compiled.params.values())


if __name__ == "__main__":
    unittest.main()
