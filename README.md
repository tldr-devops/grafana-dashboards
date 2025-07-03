# Grafana Dashboards Generator

A Python tool for building Grafana dashboards from Jinja2 templates and converting existing dashboards into reusable templates. This tool allows you to create dynamic, parameterized dashboards that can be easily maintained and deployed across different environments.

## Features

- **Template-based Dashboard Generation**: Create dashboards using Jinja2 templates with variables
- **Multi-datasource Support**: Generate dashboards for different datasources (InfluxDB, Prometheus, etc.)
- **Multiple Output Formats**: Export dashboards as JSON or YAML
- **Dashboard Conversion**: Convert existing Grafana dashboards into reusable templates
- **Flexible Configuration**: Configure outputs, datasources, and labels via YAML config

## Installation

### Requirements

- Python 3.13+
- Dependencies listed in `pyproject.toml`

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd grafana-dashboards
```

2. Install dependencies:
```bash
pip install -r requirements.txt
# or if using pip directly:
pip install jinja2>=3.1.6 pyyaml>=6.0.2
```

## Usage

### Building Templates

Generate dashboards from templates:

```bash
python3 builder.py build --config config.yml --templates templates --output output
```

**Parameters:**
- `--config`: Configuration file path (default: `config.yml`)
- `--templates`: Templates directory path (default: `templates`)
- `--output`: Output directory path (default: `output`)

### Converting Existing Dashboards

Convert existing Grafana dashboards to templates:

```bash
# Convert JSON dashboard
python3 builder.py convert --input dashboard.json --templates templates

# Convert YAML dashboard
python3 builder.py convert --input dashboard.yaml --templates templates
```

**Parameters:**
- `--input`: Path to dashboard JSON or YAML file (required)
- `--templates`: Templates directory path (default: `templates`)

## Configuration

### config.yml

```yaml
output_format:
  - json
  - yaml

datasource:
  - influxdb
  - prometheus

labels:
  - host
  - name
  - env
  - namespace
  - pod

target:
  - dashboards
```

**Configuration Options:**
- `output_format`: List of output formats (`json`, `yaml`)
- `datasource`: List of datasources to generate dashboards for
- `labels`: List of labels/variables to use in templates
- `target`: List of target types to generate (`dashboards`, `alerts`, etc.)

## Template Structure

Templates are organized in numbered directories:

```
templates/
├── 01_targets/          # Query targets/metrics
│   ├── cpu_usage.yml.j2
│   └── memory_usage.yml.j2
├── 01_variables/        # Dashboard variables
│   ├── hostname.yml.j2
│   └── environment.yml.j2
├── 01_inputs/           # Datasource inputs
│   └── prometheus.yml.j2
├── 02_panels/           # Individual panels
│   ├── cpu_panel.yml.j2
│   └── memory_panel.yml.j2
├── 03_rows/             # Row panels
│   └── system_metrics.yml.j2
└── 04_dashboards/       # Complete dashboards
    └── system_overview.yml.j2
```

### Template Syntax

Templates use `@{ }@` delimiters instead of `{{ }}` to avoid conflicts with Grafana variables:

```yaml
# Example panel template
title: "CPU Usage - @{ datasource }@"
targets:
  - expr: 'cpu_usage{@{ prom_labels(labels) }@}'
    datasource: "@{ datasource }@"
```

### Available Template Functions

- `prom_labels(labels)`: Generate Prometheus label selectors
- `influx_labels(labels)`: Generate InfluxDB WHERE clauses
- `to_nice_yaml`: Convert objects to formatted YAML

### Template Variables

- `datasource`: Current datasource being processed
- `labels`: List of available labels
- `targets`: Dictionary of rendered query targets
- `variables`: Dictionary of rendered dashboard variables
- `inputs`: Dictionary of rendered datasource inputs
- `panels`: Dictionary of rendered panels
- `rows`: Dictionary of rendered row panels
- `dashboards`: Dictionary of rendered dashboards

## Testing

The `builder.py` script has been tested with the popular [Node Exporter Full dashboard](https://grafana.com/grafana/dashboards/1860-node-exporter-full/) v41 from Grafana.com. This dashboard contains complex panels, variables, and queries that demonstrate the tool's capability to handle real-world Grafana dashboards.

```
❯ python3 builder.py convert --input node-exporter-full.json 
[✓] Converted node-exporter-full.json -> templates

❯ python3 builder.py build
***
[✓] Saved output/json/prometheus/dashboards/node_exporter_full.json
[✓] Saved output/yaml/prometheus/dashboards/node_exporter_full.yaml

❯ diff node-exporter-full.json output/json/prometheus/dashboards/node_exporter_full.json

```

### Test Example

```bash
# Download the Node Exporter Full dashboard
curl -o node-exporter-full.json "https://grafana.com/api/dashboards/1860/revisions/41/download"

# Convert to templates
python3 builder.py convert --input node-exporter-full.json --templates templates

# Build back to dashboard
python3 builder.py build --config config.yml --templates templates --output output
```

## Output Structure

Generated dashboards are organized by format, datasource, and target type:

```
output/
├── json/
│   ├── prometheus/
│   │   └── dashboards/
│   │       └── system_overview.json
│   └── influxdb/
│       └── dashboards/
│           └── system_overview.json
└── yaml/
    ├── prometheus/
    │   └── dashboards/
    │       └── system_overview.yaml
    └── influxdb/
        └── dashboards/
            └── system_overview.yaml
```

## Examples

### Creating a Simple Dashboard Template

1. Create a query target template (`templates/01_targets/cpu_usage.yml.j2`):
```yaml
expr: 'cpu_usage{@{ prom_labels(labels) }@}'
datasource: "@{ datasource }@"
refId: "A"
```

2. Create a panel template (`templates/02_panels/cpu_panel.yml.j2`):
```yaml
title: "CPU Usage"
type: "graph"
targets:
  - @{ targets["cpu_usage"] | to_nice_yaml | indent(4, false) }@
```

3. Create a dashboard template (`templates/04_dashboards/system.yml.j2`):
```yaml
title: "System Dashboard - @{ datasource }@"
panels:
  - @{ panels["cpu_panel"] | to_nice_yaml | indent(4, false) }@
```

4. Build the dashboard:
```bash
python3 builder.py build
```

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Troubleshooting

### Common Issues

1. **Template syntax errors**: Ensure you're using `@{ }@` delimiters, not `{{ }}`
2. **Missing templates**: Check that all referenced templates exist in the correct directories
3. **YAML parsing errors**: Validate your YAML syntax in template files
4. **Permission errors**: Ensure the output directory is writable

### Debug Mode

Add debug prints to see what's being processed:

```python
# Add to builder.py for debugging
print(f"Processing template: {template_path}")
print(f"Context: {template_context}")
```

## Version History

- **v0.1.0**: Initial release with basic template building and conversion features
- Tested with Node Exporter Full dashboard v41

## Support

For issues and questions, please open an issue on the project repository.
