from __future__ import annotations

import pytest

from tripsplitexpenses.categories import BUILT_IN_CATEGORIES
from tripsplitexpenses.repositories.categories import CategoryRepository


def test_custom_categories_are_trip_scoped(trip_repository, connection):
    repository = CategoryRepository(connection)
    first = trip_repository.create_trip(-100, "Japan", "SGD", 42)
    trip_repository.archive_trip(first.id, 42)
    second = trip_repository.create_trip(-200, "Korea", "SGD", 42)

    repository.create_category(first.id, "Coffee", 42)
    repository.create_category(second.id, "Coffee", 42)

    assert repository.list_category_names(first.id) == list(BUILT_IN_CATEGORIES) + ["Coffee"]
    assert repository.list_category_names(second.id) == list(BUILT_IN_CATEGORIES) + ["Coffee"]


def test_custom_category_duplicate_is_rejected(trip_repository, connection):
    repository = CategoryRepository(connection)
    trip = trip_repository.create_trip(-100, "Japan", "SGD", 42)

    repository.create_category(trip.id, "Coffee", 42)

    with pytest.raises(ValueError, match="already exists"):
        repository.create_category(trip.id, " coffee ", 42)


def test_custom_category_rename_and_delete(trip_repository, connection):
    repository = CategoryRepository(connection)
    trip = trip_repository.create_trip(-100, "Japan", "SGD", 42)
    category = repository.create_category(trip.id, "Coffee", 42)

    renamed = repository.rename_category(category.id, "Dessert")
    repository.delete_category(renamed.id, 42)

    assert repository.list_custom_categories(trip.id) == []
