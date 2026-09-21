import copy
import json

import pytest
import yaml

from callprobe.cli import main
from callprobe.loader import load_suite
from callprobe.openapi import (
    Importer,
    check_json,
    generate_openapi_suite,
    import_openapi,
    load_openapi_file,
)
from callprobe.validate import validate_suite


def doc(paths, components=None, version="3.1.0", **extra):
    out = {"openapi": version, "info": {"title": "t", "version": "1"}, "paths": paths}
    if components:
        out["components"] = components
    out.update(extra)
    return out


def op(**kw):
    return {"operationId": "op", "responses": {"200": {"description": "ok"}}, **kw}


def tool_params(document, **kw):
    result = import_openapi(document, **kw)
    return {t["name"]: t["parameters"] for t in result.tools}


def fail(document, match, **kw):
    with pytest.raises(ValueError, match=match):
        import_openapi(document, **kw)


# ------------------------------------------------------------ basic mapping


def test_maps_all_parameter_locations_and_json_body():
    document = doc({
        "/pets/{id}": {
            "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
            "post": op(
                operationId="updatePet", summary="Update", description="Long text",
                parameters=[
                    {"name": "verbose", "in": "query", "schema": {"type": "boolean"}},
                    {"name": "X-Trace", "in": "header", "required": True, "schema": {"type": "string"}},
                    {"name": "sid", "in": "cookie", "schema": {"type": "string"}},
                ],
                requestBody={"required": True, "content": {
                    "application/json": {"schema": {"type": "array", "items": {"type": "string"}}}}},
            ),
        }
    })
    result = import_openapi(document)
    (tool,) = result.tools
    assert tool["name"] == "updatePet"
    assert "POST /pets/{id}" in tool["description"] and "Update" in tool["description"]
    params = tool["parameters"]
    assert params["additionalProperties"] is False
    assert set(params["properties"]) == {"path", "query", "headers", "cookies", "body"}
    assert set(params["required"]) == {"path", "headers", "body"}
    assert params["properties"]["body"] == {"type": "array", "items": {"type": "string"}}
    assert params["properties"]["path"]["required"] == ["id"]


def test_operation_parameter_overrides_path_level_by_in_and_name():
    document = doc({"/a": {
        "parameters": [{"name": "q", "in": "query", "schema": {"type": "string"}},
                       {"name": "q", "in": "header", "schema": {"type": "string"}}],
        "get": op(parameters=[{"name": "q", "in": "query", "required": True, "schema": {"type": "integer"}}]),
    }})
    params = tool_params(document)["op"]["properties"]
    assert params["query"]["properties"]["q"] == {"type": "integer"}
    assert "q" in params["headers"]["properties"]


def test_header_names_are_case_insensitive_for_override_and_duplicates():
    document = doc({"/a": {
        "parameters": [{"name": "X-Id", "in": "header", "schema": {"type": "string"}}],
        "get": op(parameters=[{"name": "x-id", "in": "header", "schema": {"type": "integer"}}]),
    }})
    headers = tool_params(document)["op"]["properties"]["headers"]["properties"]
    assert headers == {"x-id": {"type": "integer"}}
    fail(doc({"/a": {"get": op(parameters=[
        {"name": "q", "in": "query", "schema": {}}, {"name": "q", "in": "query", "schema": {}}])}}),
        "duplicate parameter")


def test_path_parameter_rules():
    fail(doc({"/a/{id}": {"get": op()}}), "path placeholders")
    fail(doc({"/a/{id}": {"get": op(parameters=[
        {"name": "id", "in": "path", "schema": {"type": "string"}}])}}), "must be required")
    fail(doc({"/a": {"get": op(parameters=[
        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}])}}),
        "path placeholders")


def test_content_parameters_and_reserved_headers():
    fail(doc({"/a": {"get": op(parameters=[
        {"name": "f", "in": "query", "content": {"application/json": {"schema": {}}}}])}}),
        "schema is required")
    document = doc({"/a": {"get": op(parameters=[
        {"name": "Accept", "in": "header", "schema": {"type": "string"}}])}})
    result = import_openapi(document)
    assert any("reserved header" in w for w in result.warnings)
    assert "headers" not in result.tools[0]["parameters"]["properties"]


# --------------------------------------------------------------- references


def test_resolves_local_refs_with_pointer_decoding():
    document = doc(
        {"/a~1b": {"post": op(
            parameters=[{"$ref": "#/components/parameters/Limit"}],
            requestBody={"$ref": "#/components/requestBodies/Body"})}},
        {
            "parameters": {"Limit": {"name": "limit", "in": "query", "schema": {"type": "integer"}}},
            "requestBodies": {"Body": {"content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/a~1b%20c"}}}}},
            "schemas": {"a/b c": {"type": "object", "properties": {"n": {"type": "string"}}}},
        },
    )
    params = tool_params(document)["op"]["properties"]
    assert params["body"]["properties"]["n"] == {"type": "string"}
    assert params["query"]["properties"]["limit"] == {"type": "integer"}


def test_pointer_tilde_escape_is_literal_slash_and_percent_decodes_before_split():
    def body_schema(ref, schemas):
        document = doc(
            {"/a": {"post": op(requestBody={"content": {"application/json": {"schema": {"$ref": ref}}}})}},
            {"schemas": schemas},
        )
        return tool_params(document)["op"]["properties"]["body"]

    assert body_schema("#/components/schemas/x~1y", {"x/y": {"type": "string"}}) == {"type": "string"}
    nested = {"x": {"y": {"type": "integer"}}, "x/y": {"type": "string"}}
    assert body_schema("#/components/schemas/x%2Fy", nested) == {"type": "integer"}
    assert body_schema("#/components/schemas/x%7E1y", nested) == {"type": "string"}


@pytest.mark.parametrize("ref", [
    "https://example.com/schema.json", "other.yaml#/a", "#", "#/components/schemas/Nope",
    "#/components/schemas/List/-1", 5,
])
def test_external_and_unresolved_refs_fail_closed(ref):
    document = doc({"/a": {"post": op(requestBody={"content": {"application/json": {
        "schema": {"$ref": ref}}}})}}, {"schemas": {"List": [1]}})
    fail(document, "OpenAPI import failed")


def test_recursive_schema_and_ref_chain_are_rejected():
    schemas = {"Node": {"type": "object", "properties": {"next": {"$ref": "#/components/schemas/Node"}}}}
    body = {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Node"}}}}
    fail(doc({"/a": {"post": op(requestBody=body)}}, {"schemas": schemas}), "recursive reference")
    loop = {"A": {"$ref": "#/components/schemas/B"}, "B": {"$ref": "#/components/schemas/A"}}
    body["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/A"}
    fail(doc({"/a": {"post": op(requestBody=body)}}, {"schemas": loop}), "recursive reference")


def test_very_long_ref_chain_is_bounded_without_traceback():
    schemas = {f"S{i}": {"$ref": f"#/components/schemas/S{i + 1}"} for i in range(500)}
    schemas["S500"] = {"type": "string"}
    body = {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/S0"}}}}
    fail(doc({"/a": {"post": op(requestBody=body)}}, {"schemas": schemas}), "too deep")


def test_deep_schema_nesting_is_bounded():
    schema = {"type": "string"}
    for _ in range(100):
        schema = {"type": "array", "items": schema}
    body = {"content": {"application/json": {"schema": schema}}}
    fail(doc({"/a": {"post": op(requestBody=body)}}), "limit")


def test_ref_siblings_31_intersect_and_30_warn():
    schemas = {"Name": {"type": "string", "minLength": 2}}
    body = {"content": {"application/json": {"schema": {
        "$ref": "#/components/schemas/Name", "maxLength": 5}}}}
    body_schema = tool_params(doc({"/a": {"post": op(requestBody=body)}}, {"schemas": schemas}))["op"]["properties"]["body"]
    assert body_schema == {"allOf": [{"type": "string", "minLength": 2}, {"maxLength": 5}]}
    result = import_openapi(doc({"/a": {"post": op(requestBody=body)}}, {"schemas": schemas}, version="3.0.3"))
    assert any("ignores $ref siblings" in w for w in result.warnings)


def test_non_schema_ref_siblings_are_rejected_in_31():
    document = doc({"/a": {"get": op(parameters=[
        {"$ref": "#/components/parameters/P", "required": True}])}},
        {"parameters": {"P": {"name": "q", "in": "query", "schema": {}}}})
    fail(document, "reference siblings")


# ----------------------------------------------------------------- 3.0 rules


def test_nullable_and_boolean_exclusive_bounds_in_30():
    body = {"content": {"application/json": {"schema": {
        "type": "object",
        "properties": {
            "a": {"type": "string", "nullable": True},
            "b": {"type": "integer", "minimum": 1, "exclusiveMinimum": True, "maximum": 9, "exclusiveMaximum": False},
        }}}}}
    schema = tool_params(doc({"/a": {"post": op(requestBody=body)}}, version="3.0.3"))["op"]["properties"]["body"]
    assert schema["properties"]["a"]["type"] == ["string", "null"]
    assert schema["properties"]["b"] == {"type": "integer", "exclusiveMinimum": 1, "maximum": 9}


@pytest.mark.parametrize("schema, match", [
    ({"nullable": True}, "explicit type"),
    ({"type": "integer", "exclusiveMinimum": True}, "requires minimum"),
    ({"type": "integer", "exclusiveMinimum": 3}, "must be boolean"),
    ({"type": "string", "nullable": "yes"}, "nullable must be boolean"),
    ({"const": 1}, "not an OpenAPI 3.0"),
    ({"type": ["string", "null"]}, "single string"),
])
def test_30_schema_edge_cases_fail_closed(schema, match):
    body = {"content": {"application/json": {"schema": schema}}}
    fail(doc({"/a": {"post": op(requestBody=body)}}, version="3.0.3"), match)


def test_31_rejects_nullable_and_accepts_bool_schema():
    body = {"content": {"application/json": {"schema": {"type": "string", "nullable": True}}}}
    fail(doc({"/a": {"post": op(requestBody=body)}}), "nullable is not valid")
    body = {"content": {"application/json": {"schema": {
        "type": "object", "properties": {"x": True}, "additionalProperties": False}}}}
    assert tool_params(doc({"/a": {"post": op(requestBody=body)}}))["op"]["properties"]["body"]["properties"]["x"] is True


def test_preserves_combinators_and_31_types():
    schema = {"oneOf": [{"type": "string"}, {"type": ["integer", "null"]}], "not": {"const": "x"}}
    body = {"content": {"application/json": {"schema": schema}}}
    assert tool_params(doc({"/a": {"post": op(requestBody=body)}}))["op"]["properties"]["body"] == schema


@pytest.mark.parametrize("keyword", ["$defs", "unevaluatedProperties", "propertyNames", "dependentRequired", "$schema"])
def test_unsupported_semantic_keywords_are_rejected_not_dropped(keyword):
    body = {"content": {"application/json": {"schema": {"type": "object", keyword: {}}}}}
    fail(doc({"/a": {"post": op(requestBody=body)}}), "unsupported schema keyword")


def test_invalid_pattern_and_malformed_fields_do_not_traceback():
    for schema in [{"type": "string", "pattern": "("}, {"type": "object", "required": "id"},
                   {"type": "object", "required": [{"a": 1}]}, {"type": "object", "properties": []},
                   {"allOf": {"a": 1}}, {"type": "string", "description": 5}, {"type": "bogus"},
                   {"enum": "x"}, "string", 5]:
        body = {"content": {"application/json": {"schema": schema}}}
        fail(doc({"/a": {"post": op(requestBody=body)}}), "OpenAPI import failed")


def test_malformed_operation_fields_do_not_traceback():
    for bad in [op(tags="x"), op(summary=5), op(operationId=7), op(parameters={"a": 1}),
                op(parameters=[5]), op(parameters=[{"name": "q", "in": "body"}]),
                op(requestBody=5), op(requestBody={"content": {}}),
                op(requestBody={"content": {"application/json": {}}}),
                op(requestBody={"required": "yes", "content": {"application/json": {"schema": {}}}}),
                op(requestBody={"content": {"text/plain": {"schema": {"type": "string"}}}}), 5]:
        fail(doc({"/a": {"post": bad}}), "OpenAPI import failed")


# ---------------------------------------------------------------- readOnly


def test_read_only_properties_are_omitted_and_removed_from_required():
    body = {"content": {"application/json": {"schema": {
        "type": "object", "required": ["id", "name"],
        "properties": {"id": {"type": "string", "readOnly": True}, "name": {"type": "string"}}}}}}
    schema = tool_params(doc({"/a": {"post": op(requestBody=body)}}))["op"]["properties"]["body"]
    assert schema["required"] == ["name"] and set(schema["properties"]) == {"name"}


def test_read_only_through_ref_and_ref_sibling_is_omitted():
    schemas = {"Id": {"type": "string", "readOnly": True}}
    body = {"content": {"application/json": {"schema": {
        "type": "object", "required": ["id", "other"],
        "properties": {"id": {"$ref": "#/components/schemas/Id"},
                       "other": {"type": "string", "$ref": "#/components/schemas/Id", "readOnly": True}}}}}}
    schema = tool_params(doc({"/a": {"post": op(requestBody=body)}}, {"schemas": schemas}))["op"]["properties"]["body"]
    assert schema["properties"] == {} and schema["required"] == []


def test_read_only_required_from_another_allof_branch_is_rejected():
    body = {"content": {"application/json": {"schema": {"allOf": [
        {"type": "object", "properties": {"id": {"type": "string", "readOnly": True}}},
        {"type": "object", "required": ["id"]}]}}}}
    fail(doc({"/a": {"post": op(requestBody=body)}}), "readOnly")


def test_read_only_outside_property_and_with_property_counts_rejected():
    body = {"content": {"application/json": {"schema": {"type": "string", "readOnly": True}}}}
    fail(doc({"/a": {"post": op(requestBody=body)}}), "readOnly")
    body = {"content": {"application/json": {"schema": {
        "type": "object", "minProperties": 1, "properties": {"id": {"type": "string", "readOnly": True}}}}}}
    fail(doc({"/a": {"post": op(requestBody=body)}}), "minProperties")
    param = {"name": "q", "in": "query", "schema": {"type": "string", "readOnly": True}}
    fail(doc({"/a": {"get": op(parameters=[param])}}), "readOnly")


# --------------------------------------------- names, collisions, tags, skip


def test_operation_names_are_sanitised_deterministically_and_unique():
    document = doc({"/pets/{id}": {"parameters": [
        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
        "get": {}, "delete": {}, "put": {"operationId": "weird name!"}}})
    first = [t["name"] for t in import_openapi(document).tools]
    assert first == [t["name"] for t in import_openapi(copy.deepcopy(document)).tools]
    assert len(set(first)) == 3
    assert all(n.replace("_", "").replace("-", "").isalnum() and len(n) <= 64 for n in first)


def test_duplicate_operation_ids_are_hard_errors_even_with_skip():
    document = doc({"/a": {"get": op(operationId="same")}, "/b": {"get": op(operationId="same")}})
    fail(document, "duplicate operationId")
    fail(document, "duplicate operationId", skip_unsupported=True)


def test_generated_name_collision_is_detected():
    document = doc({"/a": {"get": {}}})
    name = import_openapi(document).tools[0]["name"]
    document["paths"]["/b"] = {"get": {"operationId": name}}
    fail(document, "duplicate tool name")


def test_tag_filtering_reports_counts_and_unknown_tags():
    document = doc({
        "/a": {"get": op(operationId="a", tags=["x"]), "post": op(operationId="b", tags=["y"])},
        "/c": {"get": op(operationId="c", tags=["x", "z"])},
    })
    result = import_openapi(document, tags=["x"])
    assert [t["name"] for t in result.tools] == ["a", "c"] and result.filtered == 1
    assert len(import_openapi(document, tags=["y", "z"]).tools) == 2
    fail(document, "no operations match tag.*available tags: x, y, z", tags=["nope"])
    partial = import_openapi(document, tags=["x", "nope"])
    assert any("nope" in w for w in partial.warnings)


def test_tag_filter_does_not_evaluate_unselected_unsupported_operations():
    document = doc({"/a": {"get": op(operationId="ok", tags=["x"]),
                           "post": op(operationId="bad", tags=["y"], requestBody={
                               "content": {"text/plain": {"schema": {}}}})}})
    assert len(import_openapi(document, tags=["x"]).tools) == 1


def test_strict_fails_and_skip_reports_reasons():
    document = doc({"/a": {"get": op(operationId="ok"),
                           "post": op(operationId="bad", requestBody={"content": {"multipart/form-data": {"schema": {}}}})}})
    with pytest.raises(ValueError) as strict:
        import_openapi(document)
    assert "POST /a" in str(strict.value) and "--skip-unsupported" in str(strict.value)
    result = import_openapi(document, skip_unsupported=True)
    assert [t["name"] for t in result.tools] == ["ok"]
    assert result.skipped[0]["method"] == "POST" and "JSON media" in result.skipped[0]["reason"]
    fail(doc({"/a": {"post": op(requestBody={"content": {"text/plain": {"schema": {}}}})}}),
         "no supported operations", skip_unsupported=True)


def test_multiple_media_types_prefer_json_and_warn():
    body = {"content": {"text/plain": {"schema": {"type": "string"}},
                        "application/vnd.x+json": {"schema": {"type": "integer"}},
                        "application/json; charset=utf-8": {"schema": {"type": "boolean"}}}}
    result = import_openapi(doc({"/a": {"post": op(requestBody=body)}}))
    assert result.tools[0]["parameters"]["properties"]["body"] == {"type": "boolean"}
    assert any("other media types omitted" in w for w in result.warnings)


def test_version_and_dialect_limits():
    for bad in [{"swagger": "2.0", "paths": {}}, doc({}, version="3.2.0"), doc({}, version="4.0.0"),
                {"openapi": 3.1, "paths": {}}, [], None]:
        with pytest.raises(ValueError):
            Importer(bad)
    with pytest.raises(ValueError, match="jsonSchemaDialect"):
        Importer(doc({}, jsonSchemaDialect="https://example.com/d"))
    fail({"openapi": "3.1.0"}, "paths")
    fail(doc({"/a": {"GET": op()}}), "lowercase")
    fail(doc({"nope": {}}), "invalid API path")


# ------------------------------------------------------- loading and safety


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_yaml_scalars_keep_dates_and_on_off_strings(tmp_path):
    path = write(tmp_path, "o.yaml", """
openapi: 3.0.3
paths:
  /a:
    post:
      operationId: op
      requestBody:
        content:
          application/json:
            schema:
              type: string
              enum: [on, off, yes, no, 2024-01-02, "0755", 0o17, 1e3]
""")
    enum = tool_params(load_openapi_file(path))["op"]["properties"]["body"]["enum"]
    assert enum == ["on", "off", "yes", "no", "2024-01-02", "0755", 15, 1000.0]


def test_duplicate_keys_and_non_json_values_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicate key"):
        load_openapi_file(write(tmp_path, "a.yaml", "openapi: 3.1.0\nopenapi: 3.1.0\n"))
    with pytest.raises(ValueError, match="duplicate key"):
        load_openapi_file(write(tmp_path, "a.json", '{"a": 1, "a": 2}'))
    with pytest.raises(ValueError, match="NaN"):
        load_openapi_file(write(tmp_path, "n.json", '{"a": NaN}'))
    with pytest.raises(ValueError, match="non-finite"):
        load_openapi_file(write(tmp_path, "i.yaml", "a: .inf\n"))
    with pytest.raises(ValueError, match="keys must be strings"):
        load_openapi_file(write(tmp_path, "k.yaml", "1: a\n"))
    with pytest.raises(ValueError, match="not plain JSON"):
        load_openapi_file(write(tmp_path, "t.yaml", "a: !!timestamp 2024-01-02\n"))
    with pytest.raises(ValueError, match="invalid YAML"):
        load_openapi_file(write(tmp_path, "b.yaml", "a: [unclosed\n"))
    with pytest.raises(ValueError, match="invalid YAML"):
        load_openapi_file(write(tmp_path, "p.yaml", "a: !!python/object/apply:os.system ['x']\n"))
    with pytest.raises(ValueError, match="invalid JSON"):
        load_openapi_file(write(tmp_path, "b.json", "{"))


def test_yaml_merge_keys_allow_overrides(tmp_path):
    data = load_openapi_file(write(tmp_path, "m.yaml", "base: &b {x: 1, y: 2}\nuse: {<<: *b, y: 3}\n"))
    assert data["use"] == {"x": 1, "y": 3}


def test_recursive_yaml_alias_and_alias_bomb_are_bounded(tmp_path):
    with pytest.raises(ValueError, match="recursive YAML alias"):
        load_openapi_file(write(tmp_path, "r.yaml", "a: &a\n  b: *a\n"))
    lines = ["l0: &l0 [x, x, x, x, x, x, x, x, x, x]"]
    for i in range(1, 9):
        lines.append(f"l{i}: &l{i} [" + ", ".join([f"*l{i - 1}"] * 10) + "]")
    with pytest.raises(ValueError, match="expands beyond"):
        load_openapi_file(write(tmp_path, "bomb.yaml", "\n".join(lines) + "\n"))


def test_check_json_rejects_direct_cycles_and_deep_nesting():
    cyclic = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="recursive"):
        check_json(cyclic)
    deep = current = []
    for _ in range(300):
        nxt = []
        current.append(nxt)
        current = nxt
    with pytest.raises(ValueError, match="nested too deeply"):
        check_json(deep)
    with pytest.raises(ValueError):
        Importer({"openapi": "3.1.0", "paths": {}, "x": {1, 2}})


# ------------------------------------------------------------ CLI and suite


SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "Pets", "version": "1"},
    "paths": {
        "/pets/{id}": {"put": {
            "operationId": "updatePet", "summary": "Update a pet", "tags": ["pets"],
            "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object", "required": ["name", "age"],
                "properties": {"name": {"type": "string"}, "age": {"type": "integer"}}}}}},
        }},
        "/health": {"get": {"operationId": "health", "tags": ["ops"]}},
    },
}


def spec_file(tmp_path, spec=SPEC, name="openapi.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return path


def test_cli_imports_suite_and_validate_requires_tasks_then_partial_nested_args_pass(tmp_path, capsys):
    out = tmp_path / "my-suite"
    assert main(["init", "--from-openapi", str(spec_file(tmp_path)), "--out", str(out)]) == 0
    assert {p.name for p in out.iterdir()} == {
        "tools.yaml", "distractors.yaml", "suite.yaml", "tasks.yaml", "import-report.json", "README.md"}
    tasks_text = (out / "tasks.yaml").read_text()
    assert "# - id: call-updatePet" in tasks_text and "# - id: no-call-main" in tasks_text
    assert "Update a pet" in tasks_text and '"path"' in tasks_text and "TODO" in tasks_text
    assert not [line for line in tasks_text.splitlines() if line.startswith("  - id")]
    capsys.readouterr()
    assert main(["validate", "--suite", str(out)]) == 1
    assert "no active tasks" in capsys.readouterr().out

    (out / "tasks.yaml").write_text("""\
name: my-suite
tasks:
  - id: call-updatePet
    category: select
    bundle: main
    messages:
      - role: user
        content: Rename pet 7 to Rex.
    expect:
      type: call
      tool: updatePet
      args: {path: {id: 7}, body: {name: Rex, age: 3}}
      arg_checks:
        - {path: body.name, op: eq, value: Rex}
  - id: no-call-main
    category: abstain
    bundle: main
    messages:
      - role: user
        content: Thanks!
    expect: {type: no_call}
""", encoding="utf-8")
    suite = load_suite(out)
    assert len(suite.tasks) == 2 and not validate_suite(suite)
    assert main(["validate", "--suite", str(out)]) == 0

    suite.tasks[0].expect.args = {"path": {"id": "seven"}}
    assert validate_suite(suite)


def test_incomplete_nested_args_are_rejected_by_validate(tmp_path):
    out = tmp_path / "s"
    assert main(["init", "--from-openapi", str(spec_file(tmp_path)), "--out", str(out)]) == 0
    (out / "tasks.yaml").write_text("""\
name: s
tasks:
  - id: partial
    category: select
    bundle: main
    messages: [{role: user, content: Rename pet 7.}]
    expect:
      type: call
      tool: updatePet
      args: {body: {name: Rex}}
""", encoding="utf-8")
    problems = validate_suite(load_suite(out))
    assert any("'age' is a required property" in p for p in problems)


def test_malformed_parameter_location_fails_gracefully(tmp_path, capsys):
    for location in ({"a": 1}, ["query"], 5, None):
        fail(doc({"/a": {"get": op(parameters=[{"name": "q", "in": location, "schema": {}}])}}),
             "unsupported parameter location")
    spec = doc({"/a": {"get": op(parameters=[{"name": "q", "in": {"x": 1}, "schema": {}}])}})
    assert main(["init", "--from-openapi", str(spec_file(tmp_path, spec)), "--out", str(tmp_path / "o")]) == 1
    assert "unsupported parameter location" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()


@pytest.mark.parametrize("name", ["true", "null", "on", "123", "1e3", "~", "yes", "2024-01-02", "a: b", "x y"])
def test_ambiguous_tool_names_round_trip_in_uncommented_drafts(name):
    from callprobe.init import generate_suite_files

    tools = [{"name": name, "description": "d", "parameters": {"type": "object", "properties": {}}}]
    lines = generate_suite_files(tools, "s")["tasks.yaml"].splitlines()
    block = [line.replace("  # ", "  ", 1) for line in lines if line.startswith("  #     tool:")]
    assert yaml.safe_load("\n".join(block).replace("  tool:", "tool:").strip()) == {"tool": name}


def test_cli_import_report_and_tag_flag(tmp_path, capsys):
    out = tmp_path / "s"
    assert main(["init", "--from-openapi", str(spec_file(tmp_path)), "--out", str(out), "--tag", "ops"]) == 0
    report = json.loads((out / "import-report.json").read_text())
    assert [o["tool"] for o in report["operations"]] == ["health"]
    assert report["filtered_operations"] == 1


def test_cli_strict_failure_writes_nothing_and_skip_permits(tmp_path, capsys):
    spec = copy.deepcopy(SPEC)
    spec["paths"]["/upload"] = {"post": {"operationId": "upload", "requestBody": {
        "content": {"multipart/form-data": {"schema": {"type": "object"}}}}}}
    path = spec_file(tmp_path, spec)
    out = tmp_path / "s"
    assert main(["init", "--from-openapi", str(path), "--out", str(out)]) == 1
    err = capsys.readouterr().err
    assert "POST /upload" in err and "--skip-unsupported" in err
    assert not out.exists()
    assert main(["init", "--from-openapi", str(path), "--out", str(out), "--skip-unsupported"]) == 0
    assert "skipped POST /upload" in capsys.readouterr().out
    assert "upload" in (out / "README.md").read_text()


def test_cli_overwrite_guard_preflights_and_force(tmp_path, capsys):
    path = spec_file(tmp_path)
    out = tmp_path / "s"
    out.mkdir()
    (out / "README.md").write_text("mine", encoding="utf-8")
    assert main(["init", "--from-openapi", str(path), "--out", str(out)]) == 1
    assert "README.md" in capsys.readouterr().err
    assert [p.name for p in out.iterdir()] == ["README.md"]
    assert (out / "README.md").read_text() == "mine"
    assert main(["init", "--from-openapi", str(path), "--out", str(out), "--force"]) == 0
    assert "Imported tools" in (out / "README.md").read_text()
    assert not [p for p in out.iterdir() if p.name.startswith(".")]


def test_cli_rejects_bad_option_combinations_and_inputs(tmp_path, capsys):
    path = spec_file(tmp_path)
    tools = tmp_path / "tools.json"
    tools.write_text("[]")
    for argv in (["init", "--from", str(tools), "--from-openapi", str(path)],
                 ["init"],
                 ["init", "--from", str(tools), "--tag", "x"],
                 ["init", "--from", str(tools), "--skip-unsupported"]):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2
    capsys.readouterr()
    assert main(["init", "--from-openapi", str(tmp_path / "missing.yaml"), "--out", str(tmp_path / "o")]) == 1
    (tmp_path / "bad.yaml").write_text("a: [", encoding="utf-8")
    assert main(["init", "--from-openapi", str(tmp_path / "bad.yaml"), "--out", str(tmp_path / "o")]) == 1
    assert "error:" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()


def test_cli_existing_tools_json_flow_still_works(tmp_path, capsys):
    tools = tmp_path / "tools.json"
    tools.write_text(json.dumps([{"type": "function", "function": {
        "name": "get_weather", "description": "Weather\nfor a city.",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]))
    out = tmp_path / "old"
    assert main(["init", "--from", str(tools), "--out", str(out)]) == 0
    assert {p.name for p in out.iterdir()} == {"tools.yaml", "distractors.yaml", "suite.yaml", "tasks.yaml"}
    assert "# - id: call-get_weather" in (out / "tasks.yaml").read_text()
    assert main(["init", "--from", str(tools), "--out", str(out)]) == 1
    assert main(["init", "--from", str(tools), "--out", str(out), "--force"]) == 0


def test_suite_name_is_yaml_escaped():
    files, _ = generate_openapi_suite(doc({"/a": {"get": op()}}), "weird: name # x\n- y")
    assert yaml.safe_load(files["suite.yaml"])["name"] == "weird: name # x\n- y"
    assert yaml.safe_load(files["tasks.yaml"])["name"] == "weird: name # x\n- y"


def test_openapi_descriptions_with_newlines_stay_comments():
    document = doc({"/a": {"get": op(description="line1\ntasks: [evil]\n- id: x")}})
    files, _ = generate_openapi_suite(document, "s")
    loaded = yaml.safe_load(files["tasks.yaml"])
    assert loaded["tasks"] is None
