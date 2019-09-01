#!/usr/bin/env python

import os
import argparse
import json
import re
import pathlib

import networkx
from jinja2 import Environment, FileSystemLoader

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class JsonSchema2Popo:
    """Converts a JSON Schema to a Plain Old Python Object class"""

    CLASS_TEMPLATE_FNAME = "_class.tmpl"

    J2P_TYPES = {
        "string": str,
        "integer": int,
        "number": float,
        "object": type,
        "array": list,
        "boolean": bool,
        "null": None,
    }

    def __init__(self, use_types=False, constructor_type_check=False):
        self.jinja = Environment(
            loader=FileSystemLoader(searchpath=SCRIPT_DIR), trim_blocks=True
        )
        self.jinja.filters["regex_replace"] = lambda s, find, replace: re.sub(
            find, replace, s
        )
        self.jinja.filters["any"] = any
        self.use_types = use_types
        self.constructor_type_check = constructor_type_check

        self.definitions = []

    def load(self, json_schema_file):
        self.process(json.load(json_schema_file))

    def get_model_dependencies(self, model):
        deps = set()
        for prop in model["properties"]:
            if prop["_type"]["type"] not in self.J2P_TYPES.values():
                deps.add(prop["_type"]["type"])
            if prop["_type"]["subtype"] not in self.J2P_TYPES.values():
                deps.add(prop["_type"]["subtype"])
        return list(deps)

    def process(self, json_schema):
        for _obj_name, _obj in json_schema["definitions"].items():
            model = self.definition_parser(_obj_name, _obj)
            self.definitions.append(model)

        # topological ordered dependencies
        g = networkx.DiGraph()
        models_map = {}
        for model in self.definitions:
            models_map[model["name"]] = model
            deps = self.get_model_dependencies(model)
            if not deps:
                g.add_edge(model["name"], "")
            for dep in deps:
                g.add_edge(model["name"], dep)

        self.definitions = []
        for model_name in networkx.topological_sort(g, reverse=True):
            if model_name in models_map:
                self.definitions.append(models_map[model_name])

        # create root object if there are some properties in the root
        if "properties" in json_schema:
            if "title" in json_schema:
                root_object_name = "".join(
                    x for x in json_schema["title"].title() if x.isalpha()
                )
            else:
                root_object_name = "RootObject"
            root_model = self.definition_parser(root_object_name, json_schema)
            self.definitions.append(root_model)

    def definition_parser(self, _obj_name, _obj):
        model = {"name": _obj_name}
        if "type" in _obj:
            model["type"] = self.type_parser(_obj)
            model["text_type"] = _obj["type"]

        if "enum" in _obj:
            enum = {}
            for i, v in enumerate(_obj["enum"]):
                enum[v if "javaEnumNames" not in _obj else _obj["javaEnumNames"][i]] = v
            model["enum"] = enum

        model["properties"] = []
        if "properties" in _obj:
            for _prop_name, _prop in _obj["properties"].items():
                _type = self.type_parser(_prop)
                _default = None
                if "default" in _prop:
                    _default = _type["type"](_prop["default"])
                    if _type["type"] == str:
                        _default = "'{}'".format(_default)

                _enum = None
                if "enum" in _prop:
                    _enum = _prop["enum"]

                _format = None
                if "format" in _prop:
                    _format = _prop["format"]
                if (
                    _type["type"] == list
                    and "items" in _prop
                    and isinstance(_prop["items"], list)
                ):
                    _format = _prop["items"][0]["format"]

                prop = {
                    "_name": _prop_name,
                    "_type": _type,
                    "_default": _default,
                    "_enum": _enum,
                    "_format": _format,
                }
                model["properties"].append(prop)
        return model

    def type_parser(self, t):
        _type = None
        _subtype = None
        if "type" in t:
            if t["type"] == "array" and "items" in t:
                _type = self.J2P_TYPES[t["type"]]
                if isinstance(t["items"], list):
                    if "type" in t["items"][0]:
                        _subtype = self.J2P_TYPES[t["items"][0]["type"]]
                    elif (
                        "$ref" in t["items"][0]
                        or "oneOf" in t["items"][0]
                        and len(t["items"][0]["oneOf"]) == 1
                    ):
                        if "$ref" in t["items"][0]:
                            ref = t["items"][0]["$ref"]
                        else:
                            ref = t["items"][0]["oneOf"][0]["$ref"]
                        _subtype = ref.split("/")[-1]
                elif isinstance(t["items"], dict):
                    if "type" in t["items"]:
                        _subtype = self.J2P_TYPES[t["items"]["type"]]
                    elif (
                        "$ref" in t["items"]
                        or "oneOf" in t["items"]
                        and len(t["items"]["oneOf"]) == 1
                    ):
                        if "$ref" in t["items"]:
                            ref = t["items"]["$ref"]
                        else:
                            ref = t["items"]["oneOf"][0]["$ref"]
                        _subtype = ref.split("/")[-1]
            elif isinstance(t["type"], list):
                _type = self.J2P_TYPES[t["type"][0]]
            elif t["type"]:
                _type = self.J2P_TYPES[t["type"]]
        elif "$ref" in t:
            _type = t["$ref"].split("/")[-1]
        elif "anyOf" in t or "allOf" in t or "oneOf" in t:
            _type = list
        return {"type": _type, "subtype": _subtype}

    def write_file(self, filename):
        self.jinja.get_template(self.CLASS_TEMPLATE_FNAME).stream(
            models=self.definitions,
            use_types=self.use_types,
            constructor_type_check=self.constructor_type_check,
            enum_used=any("enum" in model or any(prop._enum for prop in model.properties) for model in self.definitions)
        ).dump(filename)
        filename.close()


class readable_dir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir = values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError(
                "readable_dir:{} is not a valid path".format(prospective_dir)
            )
        if os.access(prospective_dir, os.R_OK):
            setattr(namespace, self.dest, prospective_dir)
        else:
            raise argparse.ArgumentTypeError(
                "readable_dir:{} is not a readable dir".format(prospective_dir)
            )


def init_parser():
    parser = argparse.ArgumentParser(
        description="Converts JSON Schema to Plain Old Python Object"
    )
    parser.add_argument(
        "json_schema_file",
        type=argparse.FileType("r", encoding="utf-8"),
        help="Path to JSON Schema file to load",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        type=argparse.FileType("w", encoding="utf-8"),
        help="Path to file output",
        default="model.py",
    )
    parser.add_argument(
        "-t",
        "--use-types",
        action="store_true",
        help="Add typings"
    )
    parser.add_argument(
        "-ct",
        "--constructor-type-check",
        action="store_true",
        help="Validate input types in constructor"
    )
    return parser


def main():
    parser = init_parser()
    args = parser.parse_args()

    loader = JsonSchema2Popo(use_types=args.use_types, constructor_type_check=args.constructor_type_check)
    loader.load(args.json_schema_file)

    outfile = args.output_file
    loader.write_file(outfile)

    try:
        import black

        black.format_file_in_place(
            pathlib.Path(outfile.name).absolute(),
            120,
            fast=True,
            write_back=black.WriteBack.YES,
        )
    except:
        pass


if __name__ == "__main__":
    main()
