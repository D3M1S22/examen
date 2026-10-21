"""DynamoDB I/O helpers: encoding, paging, batches, transactions, size guard.

Items hold the SQLite column names as attributes (docs/next_steps/dynamodb_storage/02 §5): ``None`` is
not written, floats are stored as ``Decimal``, JSON columns stay JSON strings. The low-level client is
used (thread-safe) with explicit (de)serialisation.
"""

from __future__ import annotations

import logging
import time
import zlib
from decimal import Decimal
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from boto3.dynamodb.types import Binary, TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

logger = logging.getLogger("examen.storage.dynamo")

_ser = TypeSerializer()
_deser = TypeDeserializer()

# Columns stored as REAL in SQLite: read back as float even when DynamoDB normalises "1.0" to "1"
FLOAT_COLUMNS = frozenset({"confidence", "latency_ms"})
COMPRESS_ABOVE = 350_000
MAX_ITEM = 400_000

# Test seam: hides items from index queries to simulate GSI propagation lag (02 §4)
INDEX_FILTER: Optional[Callable[[str, Dict[str, Any]], bool]] = None


class ItemTooLarge(Exception):
    pass


class PartialWrite(Exception):
    """Some writes of a multi-request operation did not happen; ``remaining`` lists them."""

    def __init__(self, message: str, remaining: List[Any]):
        super().__init__(message)
        self.remaining = remaining


def is_conditional_failure(error: Exception) -> bool:
    if not isinstance(error, ClientError):
        return False
    code = error.response.get("Error", {}).get("Code", "")
    if code == "ConditionalCheckFailedException":
        return True
    if code == "TransactionCanceledException":
        reasons = error.response.get("CancellationReasons") or []
        return any((r or {}).get("Code") == "ConditionalCheckFailed" for r in reasons) or not reasons
    return False


def _metric(name: str) -> None:
    try:
        from src.core.metrics import metrics

        metrics.incr(name)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def _to_ddb_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, dict):
        return {k: _to_ddb_value(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [_to_ddb_value(v) for v in value]
    return value


def encode(item: Dict[str, Any]) -> Dict[str, Any]:
    """Python item → DynamoDB wire format. ``None`` attributes are dropped."""
    return {k: _ser.serialize(_to_ddb_value(v)) for k, v in item.items() if v is not None}


def encode_value(value: Any) -> Any:
    return _ser.serialize(_to_ddb_value(value))


def _from_ddb_value(name: str, value: Any) -> Any:
    if isinstance(value, Decimal):
        if name in FLOAT_COLUMNS or value.as_tuple().exponent < 0:
            return float(value)
        return int(value)
    if isinstance(value, Binary):
        return bytes(value)
    if isinstance(value, dict):
        return {k: _from_ddb_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_ddb_value(name, v) for v in value]
    return value


def decode(item: Dict[str, Any]) -> Dict[str, Any]:
    data = {k: _from_ddb_value(k, _deser.deserialize(v)) for k, v in item.items()}
    for name in data.pop("compressed", None) or []:
        packed = data.pop(f"{name}__z", None)
        if packed is not None:
            data[name] = zlib.decompress(packed).decode("utf-8")
    return data


def _size(item: Dict[str, Any]) -> int:
    total = 0
    for key, value in item.items():
        total += len(key.encode("utf-8"))
        if isinstance(value, str):
            total += len(value.encode("utf-8"))
        elif isinstance(value, (bytes, bytearray)):
            total += len(value)
        else:
            total += 32
    return total


def pack(item: Dict[str, Any], what: str = "item") -> Dict[str, Any]:
    """Size guard: compresses the largest text attributes above ~350 KB (02 §8)."""
    if _size(item) <= COMPRESS_ABOVE:
        return item
    item = dict(item)
    candidates = sorted(
        (k for k, v in item.items() if isinstance(v, str) and (k.endswith("_json") or k.endswith("markdown")
                                                               or k in ("text", "explanatory_synthesis"))),
        key=lambda k: len(item[k]), reverse=True,
    )
    compressed = []
    for name in candidates:
        item[f"{name}__z"] = zlib.compress(item.pop(name).encode("utf-8"), 6)
        compressed.append(name)
        if _size(item) <= COMPRESS_ABOVE:
            break
    item["compressed"] = compressed
    if _size(item) > MAX_ITEM:
        _metric("storage.item_too_large")
        raise ItemTooLarge(f"{what} exceeds the DynamoDB item limit after compression")
    return item


# ---------------------------------------------------------------------------
# Table wrapper
# ---------------------------------------------------------------------------

class Expr:
    """Builds expression attribute names/values with unique placeholders."""

    def __init__(self) -> None:
        self.names: Dict[str, str] = {}
        self.values: Dict[str, Any] = {}
        self._n = 0

    def name(self, attr: str) -> str:
        for placeholder, value in self.names.items():
            if value == attr:
                return placeholder
        placeholder = f"#n{len(self.names)}"
        self.names[placeholder] = attr
        return placeholder

    def value(self, value: Any) -> str:
        self._n += 1
        placeholder = f":v{self._n}"
        self.values[placeholder] = encode_value(value)
        return placeholder

    def kwargs(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.names:
            out["ExpressionAttributeNames"] = self.names
        if self.values:
            out["ExpressionAttributeValues"] = self.values
        return out


class DynamoTable:
    """Thin wrapper over one table; ``client_getter`` returns the (possibly tenant-scoped) client."""

    def __init__(self, client_getter: Callable[[], Any], name: str):
        self._client_getter = client_getter
        self.name = name

    @property
    def client(self) -> Any:
        return self._client_getter()

    # -- single items ---------------------------------------------------------
    def get(self, key: Dict[str, Any], consistent: bool = True,
            attributes: Optional[Sequence[str]] = None) -> Optional[Dict[str, Any]]:
        kwargs: Dict[str, Any] = {"TableName": self.name, "Key": encode(key), "ConsistentRead": consistent}
        if attributes:
            e = Expr()
            kwargs["ProjectionExpression"] = ", ".join(e.name(a) for a in attributes)
            kwargs.update(e.kwargs())
        item = self.client.get_item(**kwargs).get("Item")
        return decode(item) if item else None

    def put(self, item: Dict[str, Any], condition: Optional[str] = None, expr: Optional[Expr] = None,
            what: str = "item") -> None:
        kwargs: Dict[str, Any] = {"TableName": self.name, "Item": encode(pack(item, what))}
        if condition:
            kwargs["ConditionExpression"] = condition
            if expr is not None:
                kwargs.update(expr.kwargs())
        self.client.put_item(**kwargs)

    def update(self, key: Dict[str, Any], set_: Optional[Dict[str, Any]] = None, remove: Iterable[str] = (),
               add: Optional[Dict[str, Any]] = None, set_if_absent: Optional[Dict[str, Any]] = None,
               condition: Optional[str] = None, expr: Optional[Expr] = None,
               return_values: str = "NONE") -> Optional[Dict[str, Any]]:
        e = expr or Expr()
        clauses = []
        sets = []
        for attr, value in (set_ or {}).items():
            if value is None:
                remove = list(remove) + [attr]
                continue
            sets.append(f"{e.name(attr)} = {e.value(value)}")
        for attr, value in (set_if_absent or {}).items():
            n = e.name(attr)
            sets.append(f"{n} = if_not_exists({n}, {e.value(value)})")
        if sets:
            clauses.append("SET " + ", ".join(sets))
        removes = [e.name(a) for a in dict.fromkeys(remove)]
        if removes:
            clauses.append("REMOVE " + ", ".join(removes))
        if add:
            clauses.append("ADD " + ", ".join(f"{e.name(a)} {e.value(v)}" for a, v in add.items()))
        kwargs: Dict[str, Any] = {"TableName": self.name, "Key": encode(key), "ReturnValues": return_values}
        if clauses:
            kwargs["UpdateExpression"] = " ".join(clauses)
        if condition:
            kwargs["ConditionExpression"] = condition
        kwargs.update(e.kwargs())
        response = self.client.update_item(**kwargs)
        attrs = response.get("Attributes")
        return decode(attrs) if attrs else None

    def delete(self, key: Dict[str, Any], return_old: bool = False, condition: Optional[str] = None,
               expr: Optional[Expr] = None) -> Optional[Dict[str, Any]]:
        kwargs: Dict[str, Any] = {"TableName": self.name, "Key": encode(key)}
        if return_old:
            kwargs["ReturnValues"] = "ALL_OLD"
        if condition:
            kwargs["ConditionExpression"] = condition
            if expr is not None:
                kwargs.update(expr.kwargs())
        response = self.client.delete_item(**kwargs)
        attrs = response.get("Attributes")
        return decode(attrs) if attrs else None

    # -- queries --------------------------------------------------------------
    def query(self, pk_attr: str, pk_value: str, *, index: Optional[str] = None,
              sk_attr: Optional[str] = None, begins_with: Optional[str] = None,
              between: Optional[Tuple[str, str]] = None, lt: Optional[str] = None,
              forward: bool = True, filter_expr: Optional[str] = None, expr: Optional[Expr] = None,
              attributes: Optional[Sequence[str]] = None, page_size: Optional[int] = None,
              select_count: bool = False) -> Iterator[Dict[str, Any]]:
        """Yields decoded items page by page (base table reads are consistent, index reads cannot be)."""
        e = expr or Expr()
        cond = f"{e.name(pk_attr)} = {e.value(pk_value)}"
        if sk_attr and begins_with is not None:
            cond += f" AND begins_with({e.name(sk_attr)}, {e.value(begins_with)})"
        elif sk_attr and between is not None:
            cond += f" AND {e.name(sk_attr)} BETWEEN {e.value(between[0])} AND {e.value(between[1])}"
        elif sk_attr and lt is not None:
            cond += f" AND {e.name(sk_attr)} < {e.value(lt)}"
        kwargs: Dict[str, Any] = {"TableName": self.name, "KeyConditionExpression": cond,
                                  "ScanIndexForward": forward}
        if index:
            kwargs["IndexName"] = index
        else:
            kwargs["ConsistentRead"] = True
        if filter_expr:
            kwargs["FilterExpression"] = filter_expr
        if attributes:
            kwargs["ProjectionExpression"] = ", ".join(e.name(a) for a in attributes)
        if page_size:
            kwargs["Limit"] = page_size
        if select_count:
            kwargs["Select"] = "COUNT"
        kwargs.update(e.kwargs())
        while True:
            response = self.client.query(**kwargs)
            if select_count:
                yield {"count": response.get("Count", 0)}
            for raw in response.get("Items", []):
                item = decode(raw)
                if index and INDEX_FILTER is not None and not INDEX_FILTER(index, item):
                    continue
                yield item
            last = response.get("LastEvaluatedKey")
            if not last:
                return
            kwargs["ExclusiveStartKey"] = last

    def count(self, pk_attr: str, pk_value: str, **kwargs: Any) -> int:
        return sum(page["count"] for page in self.query(pk_attr, pk_value, select_count=True, **kwargs))

    # -- batches --------------------------------------------------------------
    def batch_get(self, keys: Sequence[Dict[str, Any]], consistent: bool = True) -> List[Dict[str, Any]]:
        """Items for ``keys`` in the same order (missing items are skipped)."""
        if not keys:
            return []
        found: Dict[Tuple[str, str], Dict[str, Any]] = {}
        unique = list({(k["pk"], k["sk"]): k for k in keys}.values())
        for start in range(0, len(unique), 100):
            request = {self.name: {"Keys": [encode(k) for k in unique[start:start + 100]], "ConsistentRead": consistent}}
            attempt = 0
            while request:
                response = self.client.batch_get_item(RequestItems=request)
                for raw in response.get("Responses", {}).get(self.name, []):
                    item = decode(raw)
                    found[(item["pk"], item["sk"])] = item
                request = response.get("UnprocessedKeys") or {}
                if request:
                    attempt += 1
                    time.sleep(min(0.05 * 2 ** attempt, 2.0))
        return [found[(k["pk"], k["sk"])] for k in keys if (k["pk"], k["sk"]) in found]

    def batch_write(self, puts: Sequence[Dict[str, Any]] = (), deletes: Sequence[Dict[str, Any]] = ()) -> int:
        requests = [{"PutRequest": {"Item": encode(pack(item))}} for item in puts]
        requests += [{"DeleteRequest": {"Key": encode(key)}} for key in deletes]
        for start in range(0, len(requests), 25):
            pending = {self.name: requests[start:start + 25]}
            attempt = 0
            while pending:
                response = self.client.batch_write_item(RequestItems=pending)
                pending = response.get("UnprocessedItems") or {}
                if pending:
                    attempt += 1
                    if attempt > 10:
                        raise PartialWrite("batch write did not complete", pending.get(self.name, []))
                    time.sleep(min(0.05 * 2 ** attempt, 2.0))
        return len(requests)

    # -- transactions ---------------------------------------------------------
    def tx_put(self, item: Dict[str, Any], condition: Optional[str] = None,
               expr: Optional[Expr] = None) -> Dict[str, Any]:
        op: Dict[str, Any] = {"TableName": self.name, "Item": encode(pack(item))}
        if condition:
            op["ConditionExpression"] = condition
            if expr is not None:
                op.update(expr.kwargs())
        return {"Put": op}

    def tx_delete(self, key: Dict[str, Any], condition: Optional[str] = None,
                  expr: Optional[Expr] = None) -> Dict[str, Any]:
        op: Dict[str, Any] = {"TableName": self.name, "Key": encode(key)}
        if condition:
            op["ConditionExpression"] = condition
            if expr is not None:
                op.update(expr.kwargs())
        return {"Delete": op}

    def tx_update(self, key: Dict[str, Any], update_expression: str, expr: Expr,
                  condition: Optional[str] = None) -> Dict[str, Any]:
        op: Dict[str, Any] = {"TableName": self.name, "Key": encode(key), "UpdateExpression": update_expression,
                              **expr.kwargs()}
        if condition:
            op["ConditionExpression"] = condition
        return {"Update": op}

    def transact(self, ops: Sequence[Dict[str, Any]]) -> None:
        """One atomic transaction (≤ 100 operations): callers split work into atomic units themselves."""
        if not ops:
            return
        if len(ops) > 100:
            raise ValueError("a DynamoDB transaction holds at most 100 operations")
        self.client.transact_write_items(TransactItems=list(ops))
