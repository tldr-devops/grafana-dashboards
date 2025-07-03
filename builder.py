#!/usr/bin/env python3
"""
Grafana Template Builder & Converter

Usage:
  # Build templates into dashboards/alerts/... outputs
  python3 builder.py build --config config.yml --templates templates --output output

  # Convert existing Grafana JSON or YAML into YAML+Jinja2 templates
  python3 builder.py convert --input dashboard.json --templates templates
  python3 builder.py convert --input dashboard.yaml --templates templates
"""
import os
import json
import yaml
import uuid
import argparse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape, pass_context
from markupsafe import Markup

# Initialize Jinja2 environment
env = Environment(
    #autoescape=select_autoescape(["j2", "jinja2"]),
    variable_start_string='@{', # instead of {{ ... }}
    variable_end_string='}@',
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=False
)

def setup_loader(templates_dir):
    env.loader = FileSystemLoader(str(templates_dir))

@pass_context
def to_nice_yaml(context, value, indent=2):
    """Jinja2 filter: convert dict/list to nice YAML"""
    return yaml.dump(value, default_flow_style=False, sort_keys=False, indent=indent, allow_unicode=True)

env.filters["to_nice_yaml"] = to_nice_yaml

def write_yaml(data):
    return to_nice_yaml(None, data, indent=2).replace("'@{", "@{").replace("}@'", "}@")

# Globals for label generation
def prom_labels(labels):
    parts = [f'{lbl}="${{{lbl}}}"' for lbl in labels]
    return Markup(", ".join(parts))

env.globals['prom_labels'] = prom_labels

def influx_labels(labels):
    parts = [f"{lbl} = '${{{lbl}}}'" for lbl in labels]
    return Markup(" AND ".join(parts))
env.globals['influx_labels'] = influx_labels


def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


def render_template(path, context):
    tpl = env.get_template(path)
    return tpl.render(**context)


def render_yaml_template(path, context):
    rendered = render_template(path, context)
    # print(rendered)
    return yaml.safe_load(rendered)


def build_all(config, templates_dir, output_dir):
    datasources = config.get('datasource', [])
    labels = config.get('labels', [])
    formats = config.get('output_format', [])
    targets = config.get('target', [])

    setup_loader(templates_dir)
    type_dirs = sorted([d for d in Path(templates_dir).iterdir() if d.is_dir()], key=lambda p: p.name)

    for ds in datasources:
        ctx = {'datasource': ds, 'labels': labels}
        for d in type_dirs:
            ctx[d.name.split('_',1)[1]] = {}
        for d in type_dirs:
            key = d.name.split('_',1)[1]
            for tpl in sorted(d.glob("*.yml.j2"), key=lambda p: p.name):
                print(f"Proceed {tpl}")
                # if tpl.name.startswith("_"): continue
                rel = tpl.relative_to(templates_dir)
                data = render_yaml_template(str(rel), ctx)
                name = tpl.stem[:-4]
                ctx[key][name] = data
        for fmt in formats:
            ext = 'json' if fmt=='json' else 'yaml'
            for t in targets:
                items = ctx.get(t, {})
                for name, data in items.items():
                    if name.startswith("_"): continue
                    path = Path(output_dir)/fmt/ ds / t
                    path.mkdir(parents=True, exist_ok=True)
                    dst = path/f"{name}.{ext}"
                    with open(dst,'w') as f:
                        if fmt=='json': json.dump(data, f, indent=2, ensure_ascii=False)
                        else: yaml.dump(data, f, sort_keys=False, allow_unicode=True)
                    print(f"[✓] Saved {dst}")


def convert_dashboard(input_path, templates_dir):
    p = Path(input_path)
    data = yaml.safe_load(open(input_path)) if p.suffix.lower() in ['.yml','.yaml'] else json.load(open(input_path))

    # Directories to create
    dirs = ["01_targets", "01_variables", "01_inputs", "02_panels", "03_rows", "04_dashboards"]
    for d in dirs:
        Path(templates_dir, d).mkdir(parents=True, exist_ok=True)

    # 2) Variables
    vars_list = data.get('templating', {}).get('list', [])
    jinja_list = []
    for var in vars_list:
        name = var.get('name', uuid.uuid4())
        path = Path(templates_dir)/"01_variables"/f"{name}.yml.j2"
        with open(path,'w') as f:
            f.write(f"# Variable template: {name}\n")
            f.write(write_yaml(var))
        jinja_list.append("@{ variables[\"%s\"] | to_nice_yaml | indent(4, false) }@" % name)
    if jinja_list:
        data['templating']['list'] = jinja_list

    # 3) Inputs (datasources)
    ds_inputs = data.get('__inputs', [])
    jinja_inputs = []
    for inp in ds_inputs:
        name = inp.get('name', inp.get('pluginId', 'ds'))
        path = Path(templates_dir)/"01_inputs"/f"{name}.yml.j2"
        with open(path,'w') as f:
            f.write(f"# Datasource template: {name}\n")
            f.write(write_yaml(inp))
        jinja_inputs.append("@{ inputs[\"%s\"] | to_nice_yaml | indent(2, false) }@" % name)
    if jinja_inputs:
        data['__inputs'] = jinja_inputs

    # 1) Queries and 4) Panels
    def process_panels(panels):
        jinja_panels = []
        for panel in panels:
            panel_id = panel.get('uid') or str(panel.get('id'))
            jinja_targets = []
            for index, target in enumerate(panel.get('targets', [])):
                query_id = f"{panel_id}_t{index}"
                path = Path(templates_dir)/"01_targets"/f"{query_id}.yml.j2"
                with open(path,'w') as f:
                    f.write(f"# Query template: {query_id}\n")
                    f.write(write_yaml(target))
                jinja_targets.append("@{ targets[\"%s\"] | to_nice_yaml | indent(2, false) }@" % query_id)
            if jinja_targets:
                panel['targets'] = jinja_targets

            subpanels = panel.get('panels', [])
            if subpanels:
                path = Path(templates_dir)/"03_rows"/f"{panel_id}.yml.j2"
                jinja_panels.append("@{ rows[\"%s\"] | to_nice_yaml | indent(2, false) }@" % panel_id)
                panel['panels'] = process_panels(subpanels)
            else:
                path = Path(templates_dir)/"02_panels"/f"{panel_id}.yml.j2"
                jinja_panels.append("@{ panels[\"%s\"] | to_nice_yaml | indent(2, false) }@" % panel_id)

            # panel.pop('gridPos', None)
            with open(path,'w') as f:
                f.write(f"# Panel template: {panel_id}\n")
                f.write(write_yaml(panel))
        return jinja_panels
    panels = data.get('panels', [])
    if panels:
        data['panels'] = process_panels(panels)

    # 6) Dashboard
    name = data.get('title','dashboard').lower().replace(' ','_')
    path = Path(templates_dir)/"04_dashboards"/f"{name}.yml.j2"
    with open(path,'w') as f:
        f.write(f"# Dashboard template: {data.get('title')}\n")
        f.write(write_yaml(data))
    # print(data)
    print(f"[✓] Converted {input_path} -> {templates_dir}")


def main():
    parser = argparse.ArgumentParser(description="Grafana Template Builder & Converter")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_build = sub.add_parser('build', help='Build templates into outputs')
    p_build.add_argument('--config', default='config.yml')
    p_build.add_argument('--templates', default='templates')
    p_build.add_argument('--output', default='output')

    p_conv = sub.add_parser('convert', help='Convert Grafana dashboard JSON or YAML into templates')
    p_conv.add_argument('--input', required=True, help='Path to dashboard.json or dashboard.yml')
    p_conv.add_argument('--templates', default='templates')

    args = parser.parse_args()
    if args.cmd == 'build':
        cfg = load_config(args.config)
        build_all(cfg, args.templates, args.output)
    elif args.cmd == 'convert':
        convert_dashboard(args.input, args.templates)

if __name__ == '__main__':
    main()
