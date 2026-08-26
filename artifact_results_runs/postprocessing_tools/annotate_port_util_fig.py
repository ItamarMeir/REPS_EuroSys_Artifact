"""
Annotated re-plot of the port-utilization/queue-size figures (fig_1, fig_3, fig_6 family).

Reads already-generated raw data from artifact_results/<fig>/data/ (produced by the
original artifact_scripts/fig_*.py run) and re-creates the plot with:
  - a real per-port legend (the original scripts build the legend handles but leave the
    ax.legend(...) call commented out)
  - a figure-level headline (suptitle) describing the experiment

Does NOT touch artifact_scripts/ or artifact_results/ — reads only, writes to an
out-dir of your choosing. Does NOT re-run htsim (uses existing data files).

Usage: python3 annotate_port_util_fig.py <results_dir> <fig_dir_name> <out_dir> <output_basename> <headline>
Example:
  python3 annotate_port_util_fig.py /workspace/artifact_results_runs/quick fig_1_symmetric_micro \
      /workspace/artifact_results_runs/quick/postprocessed_plots symmetric_micro \
      "Fig 1 - Symmetric topology micro-benchmark (128-host, 2-tier, no failures)"
"""
import re
import os
import sys
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib import gridspec
import matplotlib

matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42

LINK_SPEED_Gbps = 400
PACKET_SIZE_BYTES = 4096
TIME_INTERVAL_NS = 20000
ls_number = 0
pattern = r"LS0->US(\d+)"

dark2_hex_colors = [
    '#1b9e77', '#d95f02', '#7570b3', '#e7298a',
    '#66a61e', '#e6ab02', '#a6761d', '#666666'
]


def load_port_utilization(file_path):
    data = []
    with open(file_path, 'r') as f:
        for line in f:
            ts_str = line.split(',', 1)[0]
            try:
                ts = int(ts_str)
            except ValueError:
                continue
            m = re.search(pattern, line)
            if m:
                data.append((ts, m.group(1)))
    df = pd.DataFrame(data, columns=['timestamp_ns', 'output_port'])
    df['time_bin'] = (df['timestamp_ns'] // TIME_INTERVAL_NS) * TIME_INTERVAL_NS
    util = df.groupby(['time_bin', 'output_port']).size().reset_index(name='packets')
    util['utilization'] = (util['packets'] * PACKET_SIZE_BYTES * 8) / TIME_INTERVAL_NS
    return df, util


def load_queues(queue_folder, unique_ports, prefix):
    queue_data = {}
    for port in unique_ports:
        qfile = os.path.join(queue_folder, f'{prefix}queueSizeLS{ls_number}->US{port}.txt')
        if os.path.exists(qfile):
            qdf = pd.read_csv(qfile, header=None, names=['timestamp_ns', 'queue_size_bytes'])
            qdf['queue_size_bytes'] = qdf['queue_size_bytes'] * LINK_SPEED_Gbps / 8 / 1e3
            queue_data[port] = qdf
    return queue_data


def plot_panel(ax_util, ax_queue, file_path, queue_folder, prefix, title):
    df, util = load_port_utilization(file_path)
    unique_ports = sorted(df['output_port'].unique())
    port_colors = {p: dark2_hex_colors[i] for i, p in enumerate(unique_ports)}
    queue_data = load_queues(queue_folder, unique_ports, prefix)

    for port in unique_ports:
        pu = util[util['output_port'] == port]
        sns.lineplot(data=pu, x='time_bin', y='utilization', ax=ax_util,
                     color=port_colors[port], marker='o')

    for port, qdf in queue_data.items():
        sns.lineplot(data=qdf, x='timestamp_ns', y='queue_size_bytes', ax=ax_queue,
                      color=port_colors[port], alpha=0.7)

    ax_util.set_ylim(0, 450)
    ax_util.set_xticklabels([f'{int(x / 1e3)}' for x in ax_util.get_xticks()])
    ax_util.grid(True, which='both', linestyle=':', linewidth=0.75, alpha=0.75)
    ax_queue.axhline(20 * 4096 / 1e3, color='gray', linestyle=':', linewidth=3)
    ax_queue.axhline(80 * 4096 / 1e3, color='gray', linestyle=':', linewidth=3)
    ax_util.set_title(title)

    handles = [plt.Line2D([0], [0], color=port_colors[p], lw=2) for p in unique_ports]
    labels = [f'Output port {p}' for p in unique_ports]
    ax_util.legend(handles, labels, loc='upper left', bbox_to_anchor=(1.06, 1.0),
                    fontsize=9, ncol=1, framealpha=0.9, borderaxespad=0)


def main():
    if len(sys.argv) != 6:
        print(__doc__)
        sys.exit(1)
    results_dir, fig_dir, out_dir, out_base, headline = sys.argv[1:6]
    os.makedirs(out_dir, exist_ok=True)

    data_dir = os.path.join(results_dir, fig_dir, "data")
    file_pathreps = os.path.join(data_dir, f'portSwitch_LowerPod_{ls_number}_.txt')
    file_pathobs = os.path.join(data_dir, f'obsportSwitch_LowerPod_{ls_number}_.txt')

    plt.rcParams.update({
        'axes.titlesize': 16, 'axes.labelsize': 14, 'xtick.labelsize': 12,
        'ytick.labelsize': 12, 'legend.fontsize': 9, 'figure.titlesize': 16
    })

    fig = plt.figure(figsize=(9, 6))
    gs = gridspec.GridSpec(2, 1, height_ratios=[1, 1])

    ax1 = plt.subplot(gs[0])
    ax2 = ax1.twinx()
    plot_panel(ax1, ax2, file_pathobs, data_dir, 'obs', 'Oblivious Packet Spraying')
    ax1.set_zorder(ax2.get_zorder() + 1)
    ax1.patch.set_visible(False)

    ax3 = plt.subplot(gs[1])
    ax4 = ax3.twinx()
    plot_panel(ax3, ax4, file_pathreps, data_dir, '', 'REPS')
    ax3.set_zorder(ax4.get_zorder() + 1)
    ax3.patch.set_visible(False)

    ax1.set_xlabel('')
    ax3.set_xlabel('Time (microseconds)')
    ax1.set_ylabel('')
    ax2.set_ylabel('')
    ax3.set_ylabel('')
    ax4.set_ylabel('')

    fig.text(0.99, 0.5, 'Queue Size (KB); dotted lines = ECN min/max thresholds',
              ha='center', va='center', rotation='vertical', fontsize=10)
    fig.text(0, 0.5, 'Output Port Utilization (Gbps)',
              ha='center', va='center', rotation='vertical', fontsize=12)

    fig.suptitle(headline, fontsize=13, y=1.02)

    plt.tight_layout()
    out_png = os.path.join(out_dir, f"{out_base}_annotated.png")
    plt.savefig(out_png, bbox_inches='tight')
    print(f"wrote {out_png}")


if __name__ == '__main__':
    main()
