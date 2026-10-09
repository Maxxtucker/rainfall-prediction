"""Redraw saved common-sample reliability statistics; no model fitting or evaluation."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import LogLocator, LogFormatterMathtext

parser = argparse.ArgumentParser()
parser.add_argument('--input', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
frame = pd.concat([pd.read_csv(p) for p in sorted(args.input.glob('part-*.csv'))], ignore_index=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelsize':9,
    'axes.titlesize':10,'axes.spines.top':False,'axes.spines.right':False,
    'axes.edgecolor':'#9BA8AF','text.color':'#243844','axes.labelcolor':'#243844',
    'grid.color':'#E7ECEF','pdf.fonttype':42,'svg.fonttype':'none'})
fig, axes = plt.subplots(2,2, figsize=(7.1,4.75), gridspec_kw={'height_ratios':[2.1,1], 'hspace':.53,'wspace':.35})
for col, (mode, name, color, limit) in enumerate([
    ('short_term','A: recent rainfall','#087F8C',1.0),
    ('calendar','B: calendar only','#CE684F',.16)]):
    data=frame[(frame.model==mode)&(frame.threshold==1)].sort_values('bin')
    if int(data.n.sum()) != 5729508:
        raise ValueError('Unexpected common-sample count')
    ax=axes[0,col]
    ax.plot([0,limit],[0,limit],ls='--',lw=1,color='#71828D',label='Perfect calibration')
    ax.plot(data.mean_probability,data.event_rate,'o-',color=color,lw=1.2,ms=4.5)
    ax.set(xlim=(0,limit),ylim=(0,limit),xlabel='Mean predicted probability',
           ylabel='Observed event frequency', title=name + (' (zoomed)' if col else ''))
    ax.grid(alpha=.65,zorder=0)
    if not col: ax.legend(loc='upper left',fontsize=7,frameon=False)
    else:
        ax.set_xticks([0,.04,.08,.12,.16])
        ax.set_yticks([0,.04,.08,.12,.16])
    ax=axes[1,col]
    x=(data['bin'].to_numpy()+.5)/10
    ax.bar(x,data.n.to_numpy(),width=.085,color=color,alpha=.85,zorder=3)
    ax.set(xlim=(0,1),ylim=(1e3,1e7),yscale='log',xlabel='Predicted probability bin',ylabel='Samples (log scale)')
    ax.set_xticks([0,.2,.4,.6,.8,1])
    ax.yaxis.set_major_locator(LogLocator(base=10,numticks=5))
    ax.yaxis.set_major_formatter(LogFormatterMathtext())
    ax.grid(axis='y',alpha=.65,zorder=0)
    ax.tick_params(axis='both',labelsize=8)
    if col:
        ax.text(.28,3e5,'5,726,995 below 0.1\n2,513 from 0.1 to 0.2',fontsize=8,va='center')
fig.subplots_adjust(left=.085,right=.99,bottom=.105,top=.94)
args.output.parent.mkdir(parents=True,exist_ok=True)
for ext in ['pdf','png','svg']:
    fig.savefig(args.output.with_suffix('.'+ext),dpi=200,bbox_inches='tight',pad_inches=.03)
plt.close(fig)
