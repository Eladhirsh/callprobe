"""Safe, unambiguous YAML mappings for experiment settings and CI policies."""
from __future__ import annotations

import yaml


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


class _MappingError(ValueError):
    """A diagnostic composed only from mapping-key metadata."""


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False) -> dict:
    mapping = {}
    for key_node, value_node in node.value:
        if not isinstance(key_node, yaml.ScalarNode) or key_node.tag != 'tag:yaml.org,2002:str':
            raise _MappingError('mapping keys must be strings; YAML merge keys are not supported')
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise _MappingError(f'duplicate key: {key!r}')
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_config_mapping(text: str, *, label: str) -> dict:
    """Reject duplicate/merge keys at any depth; never echo YAML value text."""
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, 'problem_mark', None)
        where = f' at line {mark.line + 1}, column {mark.column + 1}' if mark else ''
        raise ValueError(f'{label}: invalid YAML syntax{where}') from None
    except _MappingError as exc:
        raise ValueError(f'{label}: {exc}') from None
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise ValueError(f'{label}: invalid YAML syntax') from None
    if not isinstance(data, dict):
        raise ValueError(f'{label}: file must contain a YAML mapping')
    return data
