#!/usr/bin/env python3
"""
Grafana Template Builder & Converter

A tool for building Grafana dashboards from Jinja2 templates and converting 
existing dashboards into reusable templates.

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

# Initialize Jinja2 environment with custom delimiters to avoid conflicts
# with Grafana's variable syntax
jinja_env = Environment(
    # Use @{ }@ instead of {{ }} to avoid conflicts with Grafana variables
    variable_start_string='@{',
    variable_end_string='}@',
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=False
)

def setup_template_loader(templates_directory):
    """Set up the Jinja2 template loader for the specified directory."""
    jinja_env.loader = FileSystemLoader(str(templates_directory))

@pass_context
def to_nice_yaml(context, value, indent=2):
    """
    Jinja2 filter: Convert dict/list to nicely formatted YAML.

    Args:
        context: Jinja2 context (automatically passed)
        value: The value to convert to YAML
        indent: Number of spaces for indentation

    Returns:
        str: Formatted YAML string
    """
    return yaml.dump(value, default_flow_style=False, sort_keys=False, 
                    indent=indent, allow_unicode=True)

# Register the custom filter
jinja_env.filters["to_nice_yaml"] = to_nice_yaml

def write_yaml_content(data):
    """
    Write data as YAML with proper handling of Jinja2 variables.

    Args:
        data: Data to convert to YAML

    Returns:
        str: YAML string with unescaped Jinja2 variables
    """
    yaml_content = to_nice_yaml(None, data, indent=2)
    # Unescape Jinja2 variables that were quoted by YAML
    return yaml_content.replace("'@{", "@{").replace("}@'", "}@")

def create_prometheus_labels(labels):
    """
    Generate Prometheus label selector string from label list.

    Args:
        labels: List of label names

    Returns:
        Markup: Prometheus-formatted label selector
    """
    label_parts = [f'{label}="${{{label}}}"' for label in labels]
    return Markup(", ".join(label_parts))

def create_influxdb_labels(labels):
    """
    Generate InfluxDB WHERE clause from label list.

    Args:
        labels: List of label names

    Returns:
        Markup: InfluxDB-formatted WHERE clause
    """
    label_parts = [f"{label} = '${{{label}}}'" for label in labels]
    return Markup(" AND ".join(label_parts))

# Register global functions for templates
jinja_env.globals['prom_labels'] = create_prometheus_labels
jinja_env.globals['influx_labels'] = create_influxdb_labels

def load_configuration(config_path):
    """
    Load YAML configuration file.

    Args:
        config_path: Path to the configuration file

    Returns:
        dict: Configuration data
    """
    with open(config_path) as config_file:
        return yaml.safe_load(config_file)

def render_template(template_path, context):
    """
    Render a Jinja2 template with the given context.

    Args:
        template_path: Path to the template file
        context: Template context variables

    Returns:
        str: Rendered template content
    """
    template = jinja_env.get_template(template_path)
    return template.render(**context)

def render_yaml_template(template_path, context):
    """
    Render a YAML template and parse it as YAML.

    Args:
        template_path: Path to the template file
        context: Template context variables

    Returns:
        dict: Parsed YAML data
    """
    rendered_content = render_template(template_path, context)
    return yaml.safe_load(rendered_content)

def build_all_templates(config, templates_dir, output_dir):
    """
    Build all templates for all configured datasources and output formats.

    Args:
        config: Configuration dictionary
        templates_dir: Directory containing template files
        output_dir: Directory for output files
    """
    datasources = config.get('datasource', [])
    labels = config.get('labels', [])
    output_formats = config.get('output_format', [])
    target_types = config.get('target', [])

    setup_template_loader(templates_dir)

    # Get all template type directories (e.g., 01_targets, 02_panels, etc.)
    template_type_dirs = sorted([d for d in Path(templates_dir).iterdir() if d.is_dir()], 
                               key=lambda p: p.name)

    # Process each datasource
    for datasource in datasources:
        print(f"Processing datasource: {datasource}")

        # Initialize context with datasource and labels
        template_context = {'datasource': datasource, 'labels': labels}

        # Initialize empty dictionaries for each template type
        for template_dir in template_type_dirs:
            template_type = template_dir.name.split('_', 1)[1]
            template_context[template_type] = {}

        # Process each template type directory
        for template_dir in template_type_dirs:
            template_type = template_dir.name.split('_', 1)[1]

            # Process all .yml.j2 files in the directory
            for template_file in sorted(template_dir.glob("*.yml.j2"), key=lambda p: p.name):
                print(f"Processing template: {template_file}")

                # Get relative path and render template
                relative_path = template_file.relative_to(templates_dir)
                rendered_data = render_yaml_template(str(relative_path), template_context)

                # Extract name without .yml.j2 extension
                template_name = template_file.stem[:-4]  # Remove .yml.j2
                template_context[template_type][template_name] = rendered_data

        # Generate output files in requested formats
        for output_format in output_formats:
            file_extension = 'json' if output_format == 'json' else 'yaml'

            for target_type in target_types:
                target_items = template_context.get(target_type, {})

                for item_name, item_data in target_items.items():
                    # Skip private templates (starting with _)
                    if item_name.startswith("_"):
                        continue

                    # Create output directory structure
                    output_path = Path(output_dir) / output_format / datasource / target_type
                    output_path.mkdir(parents=True, exist_ok=True)

                    # Write output file
                    output_file = output_path / f"{item_name}.{file_extension}"
                    with open(output_file, 'w') as f:
                        if output_format == 'json':
                            json.dump(item_data, f, indent=2, ensure_ascii=False)
                        else:
                            yaml.dump(item_data, f, sort_keys=False, allow_unicode=True)

                    print(f"[✓] Saved {output_file}")

def convert_dashboard_to_templates(input_path, templates_dir):
    """
    Convert an existing Grafana dashboard JSON/YAML into Jinja2 templates.

    Args:
        input_path: Path to the input dashboard file
        templates_dir: Directory to save generated templates
    """
    input_file = Path(input_path)

    # Load dashboard data (JSON or YAML)
    if input_file.suffix.lower() in ['.yml', '.yaml']:
        dashboard_data = yaml.safe_load(open(input_path))
    else:
        dashboard_data = json.load(open(input_path))

    # Create template directory structure
    template_directories = [
        "01_targets",     # Query targets
        "01_variables",   # Dashboard variables
        "01_inputs",      # Datasource inputs
        "02_panels",      # Individual panels
        "03_rows",        # Row panels
        "04_dashboards"   # Complete dashboards
    ]

    for directory in template_directories:
        Path(templates_dir, directory).mkdir(parents=True, exist_ok=True)

    # Process dashboard variables
    variables_list = dashboard_data.get('templating', {}).get('list', [])
    jinja_variables_list = []

    for variable in variables_list:
        variable_name = variable.get('name', str(uuid.uuid4()))
        variable_template_path = Path(templates_dir) / "01_variables" / f"{variable_name}.yml.j2"

        with open(variable_template_path, 'w') as f:
            f.write(f"# Variable template: {variable_name}\n")
            f.write(write_yaml_content(variable))

        jinja_variables_list.append(f"@{{ variables[\"{variable_name}\"] | to_nice_yaml | indent(4, false) }}@")

    if jinja_variables_list:
        dashboard_data['templating']['list'] = jinja_variables_list

    # Process datasource inputs
    datasource_inputs = dashboard_data.get('__inputs', [])
    jinja_inputs_list = []

    for input_config in datasource_inputs:
        input_name = input_config.get('name', input_config.get('pluginId', 'ds'))
        input_template_path = Path(templates_dir) / "01_inputs" / f"{input_name}.yml.j2"

        with open(input_template_path, 'w') as f:
            f.write(f"# Datasource template: {input_name}\n")
            f.write(write_yaml_content(input_config))

        jinja_inputs_list.append(f"@{{ inputs[\"{input_name}\"] | to_nice_yaml | indent(2, false) }}@")

    if jinja_inputs_list:
        dashboard_data['__inputs'] = jinja_inputs_list

    def process_panel_list(panels):
        """
        Recursively process panels and their queries, creating templates.

        Args:
            panels: List of panel dictionaries

        Returns:
            list: List of Jinja2 template references
        """
        jinja_panels_list = []

        for panel in panels:
            panel_id = panel.get('uid') or str(panel.get('id', uuid.uuid4()))

            # Process panel queries/targets
            jinja_targets_list = []
            for target_index, target in enumerate(panel.get('targets', [])):
                query_id = f"{panel_id}_t{target_index}"
                query_template_path = Path(templates_dir) / "01_targets" / f"{query_id}.yml.j2"

                with open(query_template_path, 'w') as f:
                    f.write(f"# Query template: {query_id}\n")
                    f.write(write_yaml_content(target))

                jinja_targets_list.append(f"@{{ targets[\"{query_id}\"] | to_nice_yaml | indent(2, false) }}@")

            if jinja_targets_list:
                panel['targets'] = jinja_targets_list

            # Handle nested panels (for row panels)
            subpanels = panel.get('panels', [])
            if subpanels:
                # This is a row panel
                panel_template_path = Path(templates_dir) / "03_rows" / f"{panel_id}.yml.j2"
                jinja_panels_list.append(f"@{{ rows[\"{panel_id}\"] | to_nice_yaml | indent(2, false) }}@")
                panel['panels'] = process_panel_list(subpanels)
            else:
                # This is a regular panel
                panel_template_path = Path(templates_dir) / "02_panels" / f"{panel_id}.yml.j2"
                jinja_panels_list.append(f"@{{ panels[\"{panel_id}\"] | to_nice_yaml | indent(2, false) }}@")

            # Save panel template
            with open(panel_template_path, 'w') as f:
                f.write(f"# Panel template: {panel_id}\n")
                f.write(write_yaml_content(panel))

        return jinja_panels_list

    # Process all panels
    panels = dashboard_data.get('panels', [])
    if panels:
        dashboard_data['panels'] = process_panel_list(panels)

    # Save main dashboard template
    dashboard_name = dashboard_data.get('title', 'dashboard').lower().replace(' ', '_')
    dashboard_template_path = Path(templates_dir) / "04_dashboards" / f"{dashboard_name}.yml.j2"

    with open(dashboard_template_path, 'w') as f:
        f.write(f"# Dashboard template: {dashboard_data.get('title', 'Unknown Dashboard')}\n")
        f.write(write_yaml_content(dashboard_data))

    print(f"[✓] Converted {input_path} -> {templates_dir}")

def main():
    """Main entry point for the CLI application."""
    parser = argparse.ArgumentParser(
        description="Grafana Template Builder & Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build templates into outputs
  python3 builder.py build --config config.yml --templates templates --output output

  # Convert existing dashboard to templates
  python3 builder.py convert --input dashboard.json --templates templates
        """
    )

    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')

    # Build command
    build_parser = subparsers.add_parser('build', help='Build templates into outputs')
    build_parser.add_argument('--config', default='config.yml', 
                             help='Configuration file path (default: config.yml)')
    build_parser.add_argument('--templates', default='templates', 
                             help='Templates directory path (default: templates)')
    build_parser.add_argument('--output', default='output', 
                             help='Output directory path (default: output)')

    # Convert command
    convert_parser = subparsers.add_parser('convert', 
                                          help='Convert Grafana dashboard JSON or YAML into templates')
    convert_parser.add_argument('--input', required=True, 
                               help='Path to dashboard.json or dashboard.yml file')
    convert_parser.add_argument('--templates', default='templates', 
                               help='Templates directory path (default: templates)')

    args = parser.parse_args()

    try:
        if args.command == 'build':
            configuration = load_configuration(args.config)
            build_all_templates(configuration, args.templates, args.output)
            print("✓ Build completed successfully!")

        elif args.command == 'convert':
            convert_dashboard_to_templates(args.input, args.templates)
            print("✓ Conversion completed successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0

if __name__ == '__main__':
    exit(main())
