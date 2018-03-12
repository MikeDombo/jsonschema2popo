#!/usr/bin/env python

import os
import argparse
import json
from jinja2 import Environment, FileSystemLoader

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

class JsonSchema2Popo(object):
    """Converts a JSON Schema to a Plain Old Python Object class"""
    definitions = []

    TEMPLATES_FOLDER = 'templates/'
    CLASS_TEMPLATE_FNAME = '_class.tmpl'
    
    J2P_TYPES = {
        'string': 'str',
        'integer': 'int',
        'number': 'float',
        'object': 'type',
        'array': 'list',
        'boolean': 'bool',
        'null': 'None'
    }
    
    def __init__(self):
        self.jinja = Environment(loader=FileSystemLoader(os.path.join(os.path.sep, SCRIPT_DIR, self.TEMPLATES_FOLDER)), trim_blocks=True)

    def load(self, json_schema_file):
        self.process(json.load(json_schema_file))

    def process(self, json_schema):
        for _obj_name, _obj in json_schema['definitions'].items():
            model = {}
            model['name'] = _obj_name
            model['properties'] = []
            model['defaults'] = []
            for _prop_name, _prop in _obj['properties'].items():
                if 'default' in _prop:
                    _prop_value = _prop['default']
                    if _prop['type'] == 'string':
                        _prop_value = "'{}'".format(_prop_value)
                    model['defaults'].append({
                        '_name': _prop_name,
                        '_value': _prop_value
                    })
                
                prop = {
                    '_name': _prop_name,
                    '_type': self.J2P_TYPES[_prop['type']]
                }
                if 'enum' in _prop:
                    prop['enum'] = {
                        '_name': "%sTypes" % (_prop_name.capitalize(), ),
                        '_values': ' '.join(_prop['enum'])
                    }
                model['properties'].append(prop)

            model['import_enum'] = True in ['enum' in p for p in model['properties']]

            self.definitions.append(model)

    def write_folder(self, foldername):
        for definition in self.definitions:
            self.jinja.get_template(self.CLASS_TEMPLATE_FNAME) \
                .stream(model=definition) \
                .dump('{}/{}.py'.format(foldername, definition['name']))

class readable_dir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir=values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError("readable_dir:{} is not a valid path".format(prospective_dir))
        if os.access(prospective_dir, os.R_OK):
            setattr(namespace, self.dest, prospective_dir)
        else:
            raise argparse.ArgumentTypeError("readable_dir:{} is not a readable dir".format(prospective_dir))

def init_parser():
    parser = argparse.ArgumentParser(description="Converts JSON Schema to Plain Old Python Object")
    parser.add_argument('json_schema_file', type=argparse.FileType('r'), help="Path to JSON Schema file to load")
    parser.add_argument('-t', '--templates-folder', action=readable_dir, help="Path to templates folder", default=JsonSchema2Popo.TEMPLATES_FOLDER)
    parser.add_argument('-o', '--output-folder', action=readable_dir, help="Path to folder output", default="out/")
    return parser

if __name__ == '__main__':
    parser = init_parser()
    args = parser.parse_args()

    loader = JsonSchema2Popo()
    loader.load(args.json_schema_file)

    outfolder = args.output_folder
    loader.write_folder(outfolder)