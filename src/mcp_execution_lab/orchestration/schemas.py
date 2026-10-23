"""Conservative checks of published input/output types; unknown remains unknown."""


def dereference(schema, root):
    visited = set()
    while isinstance(schema, dict) and "$ref" in schema:
        reference = schema["$ref"]
        if reference in visited or not reference.startswith("#/"):
            return {}
        visited.add(reference)
        value = root
        for part in reference[2:].split("/"):
            value = value.get(part.replace("~1", "/").replace("~0", "~"), {})
        schema = value
    return schema if isinstance(schema, dict) else {}


def at_path(schema, path, root=None):
    root = schema if root is None else root
    current = dereference(schema, root)
    for part in path:
        if isinstance(part, int):
            current = current.get("items", {})
        else:
            current = current.get("properties", {}).get(part, {})
        current = dereference(current, root)
    return current, root


def types(schema, root):
    schema = dereference(schema, root)
    if "anyOf" in schema or "oneOf" in schema:
        values = [types(part, root) for part in schema.get("anyOf", schema.get("oneOf", []))]
        return None if any(value is None for value in values) else set().union(*values)
    declared = schema.get("type")
    if declared:
        return {declared} if isinstance(declared, str) else set(declared)
    return None


def incompatible(source, source_root, target, target_root):
    source_types, target_types = types(source, source_root), types(target, target_root)
    if source_types is None or target_types is None:
        return False
    if source_types & target_types:
        return False
    return not ("integer" in source_types and "number" in target_types)
