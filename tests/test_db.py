from __future__ import annotations

import pytest

from screenmemory.db import deserialize_embedding, serialize_embedding


def test_serialize_deserialize_embedding_roundtrip() -> None:
    # We use floats that can be exactly represented in IEEE-754 float32
    # to avoid precision issues in the roundtrip.
    test_cases = [
        [0.0, 1.0, -1.0, 0.5, -0.5, 1.5, -1.5],
        [1.25, -2.5, 3.125, -4.0],
        [],
    ]

    for values in test_cases:
        blob = serialize_embedding(values)
        assert isinstance(blob, bytes)

        decoded = deserialize_embedding(blob)
        assert isinstance(decoded, list)
        assert len(decoded) == len(values)

        for expected, actual in zip(values, decoded):
            assert expected == actual


def test_serialize_deserialize_precision_handling() -> None:
    # Float32 has limited precision. We can verify that
    # the roundtrip preserves values up to float32 precision limits.
    values = [0.1, 0.2, 0.3]
    blob = serialize_embedding(values)
    decoded = deserialize_embedding(blob)

    assert len(decoded) == len(values)
    for expected, actual in zip(values, decoded):
        assert actual == pytest.approx(expected, rel=1e-5)
