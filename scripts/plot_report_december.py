"""Plot saved December station totals with one 0--600 mm scale across all eight years."""
from pathlib import Path
import argparse, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.colors import Normalize
parser=argparse.ArgumentParser()
parser.add_argument('--input',type=Path,required=True)
parser.add_argument('--boundary',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
data=pd.concat([pd.read_csv(p) for p in sorted(args.input.glob('part-*.csv'))],ignore_index=True)
data=data[data.month==12]
if not data.rainfall_total_mm.between(0,600).all():
    raise ValueError('Station values exceed the shared display scale')
geo=json.loads(args.boundary.read_text())
rings=[]
for feature in geo['features']:
    geom=feature['geometry']
    if geom['type']=='MultiPolygon':rings.extend(geom['coordinates'])
    elif geom['type']=='Polygon':rings.append(geom['coordinates'])
vertices=np.concatenate([np.array(poly[0])[:,:2] for poly in rings])
bounds=(vertices[:,0].min()-.01,vertices[:,0].max()+.01,vertices[:,1].min()-.01,vertices[:,1].max()+.01)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'text.color':'#243844','axes.labelcolor':'#243844','pdf.fonttype':42,'svg.fonttype':'none'})
fig,axes=plt.subplots(2,4,figsize=(7.1,3.0),layout='constrained')
norm=Normalize(0,600)
for year,ax in zip(range(2017,2025),axes.flat):
    for poly in rings:
        for i,ring in enumerate(poly):
            ax.add_patch(Polygon(np.array(ring)[:,:2],facecolor='#F2F4F3' if i==0 else 'white',edgecolor='#A4B1B7',lw=.35))
    sample=data[data.year==year]
    ax.scatter(sample.longitude,sample.latitude,c=sample.rainfall_total_mm,cmap='YlGnBu',norm=norm,s=13,edgecolors='#71868C',linewidths=.2,zorder=3)
    ax.set(xlim=bounds[:2],ylim=bounds[2:])
    ax.set_aspect(1/np.cos(np.deg2rad(1.35)))
    ax.set_axis_off()
    ax.set_title(f'{year}  |  {len(sample)} stations',fontsize=8.5,pad=4)
bar=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap='YlGnBu'),ax=list(axes.flat),fraction=.025,pad=.015,ticks=range(0,601,100))
bar.set_label('December rainfall (mm)',fontsize=8.5)
bar.outline.set_visible(False)
args.output.parent.mkdir(parents=True,exist_ok=True)
for ext in ['pdf','png']:
    fig.savefig(args.output.with_suffix('.'+ext),dpi=200,bbox_inches='tight',pad_inches=.035)
plt.close(fig)
