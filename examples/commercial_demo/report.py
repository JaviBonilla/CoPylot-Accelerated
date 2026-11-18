"""Build the offline Plotly report for the commercial demo."""

from html import escape
import json
from pathlib import Path
from string import Template
from tempfile import TemporaryDirectory

import numpy as np
import plotly.graph_objects as go
from plotly.io import to_json
from plotly.offline import get_plotlyjs


MODE_LABELS = {"original": "Original CPU", "refactored": "Refactored CPU",
               "multicore": "Multicore CPU", "cuda": "CUDA GPU"}
FLUX_SCALE = "Inferno"
FLUX_COLORBAR = dict(title=dict(text="kW/m²"), thickness=13, len=.8)


def pairs(items):
    return "".join(f"<div><dt>{escape(label)}</dt><dd>{escape(str(value))}</dd></div>"
                   for label, value in items)


def data_json(value):
    # Keep embedded JSON inside its script element, even if text contains markup.
    return json.dumps(value, ensure_ascii=False).replace("<", r"\u003c")


def style(figure, **layout):
    figure.update_layout(template="plotly_white", margin=dict(l=64, r=35, t=30, b=55),
                         font=dict(family="system-ui, sans-serif", color="#243c48", size=12),
                         paper_bgcolor="#fff", plot_bgcolor="#f5f8fa", **layout)
    return figure


def flux_figure(data, flux, s, z, peak):
    g = data["grid"]
    fig = go.Figure(go.Heatmap(x=s, y=z, z=flux, zmin=0, zmax=peak, colorscale=FLUX_SCALE, zsmooth=False,
                             colorbar=FLUX_COLORBAR,
                             hovertemplate="Arc s %{x:.2f} m<br>Height z %{y:.2f} m<br>"
                                           "Incident flux %{z:.2f} kW/m²<extra></extra>"))
    fig.update_xaxes(title="Circumferential position s (m)", range=[0, g["surface_width_m"]], constrain="domain")
    fig.update_yaxes(title="Height above receiver bottom (m)", range=[0, g["height_m"]],
                     scaleanchor="x", scaleratio=1, constrain="domain")
    return style(fig, dragmode="zoom")


def cylindrical_flux_figure(receiver, flux, s, z, peak):
    ny, nx = flux.shape
    radius = receiver["diameter_m"] / 2
    height = receiver["height_m"]
    # Receiver.cpp uses azimuth π at the south seam, decreasing toward the east
    # in column order. Exported rows already start at the bottom.
    azimuth = np.linspace(np.pi, -np.pi, nx + 1)
    east = radius * np.sin(azimuth)
    east[[0, -1]] = 0
    north = radius * np.cos(azimuth)
    elevations = np.linspace(0, height, ny + 1)

    # Share vertices around each ring. Assign the same sample to both triangles
    # of each cell so the colors stay constant across it.
    row_width = nx + 1
    lower_left = np.arange((ny + 1) * row_width, dtype=np.int32).reshape(ny + 1, row_width)[:-1, :-1].ravel()
    upper_left = lower_left + row_width
    triangles = np.empty((2 * flux.size, 3), dtype=np.int32)
    triangles[::2] = np.column_stack((lower_left, lower_left + 1, upper_left + 1))
    triangles[1::2] = np.column_stack((lower_left, upper_left + 1, upper_left))
    s_center, z_center = np.meshgrid(s, z)
    centers = np.repeat(np.column_stack((s_center.ravel(), z_center.ravel())), 2, axis=0)
    fig = go.Figure(go.Mesh3d(
        x=np.tile(east, ny + 1), y=np.tile(north, ny + 1), z=np.repeat(elevations, row_width),
        i=triangles[:, 0], j=triangles[:, 1], k=triangles[:, 2],
        intensity=np.repeat(flux.ravel(), 2), intensitymode="cell", customdata=centers,
        cmin=0, cmax=peak, colorscale=FLUX_SCALE, showscale=True, colorbar=FLUX_COLORBAR,
        flatshading=True, lighting=dict(ambient=1, diffuse=0, specular=0, fresnel=0),
        hovertemplate="Arc s %{customdata[0]:.2f} m<br>Height z %{customdata[1]:.2f} m<br>"
                      "Incident flux %{intensity:.2f} kW/m²<extra></extra>",
    ))
    return style(fig, scene=dict(xaxis_title="East (m)", yaxis_title="North (m)", zaxis_title="Height (m)",
                                 aspectmode="data", dragmode="orbit",
                                 camera=dict(eye=dict(x=1.4, y=-1.7, z=.72),
                                             projection=dict(type="orthographic"))))


def field_figure(details, solar_azimuth_deg):
    efficiency = 100 * details["optical_efficiency_fraction"]
    fig = go.Figure([
        go.Scattergl(x=details["x_east_m"], y=details["y_north_m"], mode="markers", name="Heliostats",
                     marker=dict(size=4, color=efficiency, colorscale="Viridis",
                                 colorbar=dict(title=dict(text="Eff. (%)"), thickness=13, len=.8)),
                     customdata=np.column_stack((details["id"], efficiency, details["absorbed_receiver_power_kw"])),
                     hovertemplate="Heliostat %{customdata[0]:.0f}<br>East %{x:,.2f} m · North %{y:,.2f} m"
                                   "<br>Optical efficiency incl. receiver %{customdata[1]:.1f}%"
                                   "<br>Absorbed contribution %{customdata[2]:.2f} kW<extra></extra>"),
        go.Scatter(x=[0], y=[0], mode="markers", name="Tower",
                   marker=dict(size=11, color="#111e24", symbol="diamond", line=dict(color="white", width=1.5)),
                   hovertemplate="Tower at field origin<extra></extra>"),
    ])
    # SolarPILOT azimuth is positive eastward from north. These are coordinates
    # along the direction toward the sun, measured from the tower.
    azimuth = np.deg2rad(solar_azimuth_deg)
    distance = .16 * max(1, np.hypot(details["x_east_m"], details["y_north_m"]).max())
    east, north = distance * np.sin(azimuth), distance * np.cos(azimuth)
    arrow_color = "#7e431e"
    fig.add_annotation(x=east, y=north, ax=.12 * east, ay=.12 * north,
                       xref="x", yref="y", axref="x", ayref="y", text="", showarrow=True,
                       arrowhead=2, arrowwidth=2, arrowcolor=arrow_color)
    fig.add_annotation(x=east, y=north, text="Sun direction", yshift=-13, showarrow=False,
                       font=dict(color=arrow_color, size=11), bgcolor="rgba(255,255,255,.94)", borderpad=2)
    fig.add_annotation(x=0, y=0, xref="x", yref="y", text="Tower", yshift=8,
                       xanchor="center", yanchor="bottom", showarrow=False, captureevents=False,
                       bgcolor="white", borderpad=1)
    fig.update_xaxes(title="X East (m)", constrain="domain")
    fig.update_yaxes(title="Y North (m)", scaleanchor="x", scaleratio=1, constrain="domain")
    return style(fig, showlegend=False)


def geometry_figures(receiver):
    radius = receiver["diameter_m"] / 2
    height = receiver["height_m"]
    center = receiver["tower_optical_height_m"]
    lower, upper = center - height / 2, center + height / 2
    theta = np.linspace(-np.pi, np.pi, 73)
    fig = go.Figure(go.Surface(x=np.tile(radius * np.sin(theta), (2, 1)),
                              y=np.tile(radius * np.cos(theta), (2, 1)),
                              z=np.tile([[lower], [upper]], (1, len(theta))),
                              colorscale=[[0, "#086b79"], [1, "#8bd5cf"]], showscale=False,
                              hovertemplate="East %{x:.2f} m<br>North %{y:.2f} m<br>Elevation %{z:.2f} m<extra></extra>"))
    fig.add_scatter3d(x=[0, 0], y=[0, 0], z=[0, center], mode="lines", name="Optical height",
                      line=dict(color="#aa5c20", width=5),
                      hovertemplate="Optical axis · %{z:.3f} m<extra></extra>")
    fig.add_scatter3d(x=[0, 0], y=[-radius, -radius], z=[lower, upper], mode="lines",
                      line=dict(color="#15292f", width=5, dash="dash"), name="South seam")
    horizontal_limit = 1.6 * radius
    z_min, z_max = -height / 4, upper + height / 4
    # Scale the full height to fit the viewport while keeping equal metres per axis.
    vertical_aspect = 1.55
    horizontal_aspect = vertical_aspect * 2 * horizontal_limit / (z_max - z_min)
    style(fig, scene=dict(xaxis_title="East (m)", yaxis_title="North (m)", zaxis_title="Elevation (m)",
                          xaxis=dict(range=[-horizontal_limit, horizontal_limit], showticklabels=False),
                          yaxis=dict(range=[-horizontal_limit, horizontal_limit], showticklabels=False),
                          zaxis=dict(range=[z_min, z_max]),
                          aspectmode="manual",
                          aspectratio=dict(x=horizontal_aspect, y=horizontal_aspect, z=vertical_aspect),
                          camera=dict(eye=dict(x=1.3, y=-1.7, z=.65), projection=dict(type="orthographic"))),
          legend=dict(orientation="h", y=-.12))

    section = go.Figure()
    section.add_shape(type="rect", x0=-radius, x1=radius, y0=-height/2, y1=height/2,
                      line=dict(color="#086b79", width=2), fillcolor="#cdece8")
    section.add_hline(y=0, line_dash="dot", line_color="#4d7277")
    section.add_annotation(x=0, y=height/2 + 1, text=f"Diameter {2*radius:.2f} m",
                           showarrow=False, yanchor="bottom")
    section.add_annotation(x=radius + 1, y=0, text=f"Height {height:.4f} m",
                           showarrow=False, xanchor="left", textangle=-90)
    section.update_xaxes(title="Width (m)", range=[-radius-5, radius+8], constrain="domain")
    section.update_yaxes(title="z relative to optical center (m)", range=[-height/2-3, height/2+5],
                         scaleanchor="x", scaleratio=1, constrain="domain")
    style(section, dragmode="pan")
    return fig, section


def write_report(path, data, flux, details, s, z):
    receiver, grid, field = (data[key] for key in ("receiver", "grid", "field"))
    state, settings, metrics = (data[key] for key in ("operating_point", "configuration", "metrics"))
    fig_3d, section = geometry_figures(receiver)
    peak = metrics["peak_cell_average_proxy_kw_m2"]
    figures = {"flux-chart": flux_figure(data, flux, s, z, peak),
               "cylinder-flux-chart": cylindrical_flux_figure(receiver, flux, s, z, peak),
               "field-chart": field_figure(details, state["solar_azimuth_deg"]),
               "geometry-chart": fig_3d, "section-chart": section}
    charts = "<script type=\"application/json\" id=\"figures\">" + data_json(
        {key: json.loads(to_json(figure)) for key, figure in figures.items()}) + "</script>"
    cards = "".join(f'<div><span>{label}</span><strong>{reading}</strong></div>' for label, reading in (
        ("Heliostats", f"{field['heliostats']:,}"),
        ("DNI", f"{state['dni_w_m2']:,.0f} <small>W/m²</small>"),
        ("Field optical efficiency", f"{metrics['optical_efficiency_percent']:.2f}%"),
        ("Receiver absorbed power", f"{metrics['receiver_absorbed_power_kw']/1000:,.2f} <small>MW</small>"),
        ("Peak sampled flux", f"{metrics['peak_cell_average_proxy_kw_m2']:,.1f} <small>kW/m²</small>"),
    ))
    source_links = "".join(f'<li><a href="{escape(item["url"], quote=True)}">{escape(item["title"])}</a></li>'
                           for item in data["sources"].values() if item["url"])
    template = Template(Path(__file__).with_name("report.html.in").read_text(encoding="utf-8"))
    page = template.substitute(
        plotly_js=get_plotlyjs(), charts=charts, cards=cards,
        site=escape(state["site"]["name"]), date=escape(state["date"]), time=escape(state["local_time"]),
        mode=MODE_LABELS[settings["mode"]],
        flux_metrics=pairs([
            ("Peak sampled flux", f"{metrics['peak_cell_average_proxy_kw_m2']:,.2f} kW/m²"),
            ("Mean incident flux", f"{metrics['mean_kw_m2']:,.2f} kW/m²"),
            ("Integrated incident power", f"{metrics['integrated_incident_power_kw']/1000:,.2f} MW"),
        ]),
        field_metrics=pairs([
            ("Heliostats", f"{field['heliostats']:,}"),
            ("Heliostat dimensions", f"{field['heliostat_width_m']:g} × {field['heliostat_height_m']:g} m"),
            ("Physical mirror area", f"{field['physical_mirror_area_m2']:,.0f} m²"),
            ("Effective aperture", f"{field['effective_aperture_area_m2']:,.0f} m²"),
        ]),
        geometry=pairs([
            ("Tower optical height", f"{receiver['tower_optical_height_m']:.3f} m"),
            ("Receiver type", "External cylindrical"),
            ("Diameter", f"{receiver['diameter_m']:.2f} m"),
            ("Height", f"{receiver['height_m']:.4f} m"),
            ("Circumference", f"{receiver['circumference_m']:.3f} m"),
            ("Lateral surface area", f"{receiver['surface_area_m2']:,.2f} m²"),
            ("Absorptance", f"{receiver['absorptance']:.1%}"),
            ("Grid · columns × rows", f"{grid['nx']} × {grid['ny']}"),
            ("Cell size · arc × vertical", f"{grid['cell_width_m']:.4f} × {grid['cell_height_m']:.4f} m"),
        ]),
        operating=pairs([
            ("DNI source", state["dni_source"]),
            ("Solar azimuth / elevation", f"{state['solar_azimuth_deg']:.3f}° / {state['solar_elevation_deg']:.3f}°"),
            ("Optical model / aiming", f"{settings['optical_model']} / {settings['aiming'].split(',', 1)[0]}"),
            ("Backend / CPU threads", f"{settings['backend'].upper()} / {settings['threads']}"),
            ("Native simulate call", f"{data['timing_seconds']['simulate']:.3f} s"),
        ]),
        sources=source_links,
    )
    path.write_text(page, encoding="utf-8")


def render_saved_report(directory):
    """Replace only the HTML report after reading the existing JSON and CSV files."""
    from results import read_numerical_results

    directory = directory.resolve()
    data, flux, details, s, z = read_numerical_results(directory)
    output = directory / "report.html"
    with TemporaryDirectory(dir=directory, prefix=".commercial-report-") as temp:
        rendered = Path(temp) / output.name
        write_report(rendered, data, flux, details, s, z)
        rendered.replace(output)
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Regenerate the offline report from a saved commercial demo run.")
    parser.add_argument("directory", type=Path, help="Directory containing results.json and both CSV files")
    args = parser.parse_args()
    try:
        print(render_saved_report(args.directory))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Commercial report: {error}\n")
