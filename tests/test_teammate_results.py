"""Reconciliation failures must stop supplementary report construction."""
import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_teammate_results import reconcile_daily,compare_cohort,Q
from import_teammate_results import safe_target
from import_gbt_text import parse_export
import json


class TeammateResultTests(unittest.TestCase):
    def test_daily_brier_reconciliation_and_reject_corruption(self):
        m=pd.DataFrame({'threshold':[1.], 'n':[100], 'brier':[.02]})
        d=pd.DataFrame({'threshold':[1.,1.], 'n':[40,60], 'sum_squared_error':[.5,1.5]})
        reconcile_daily(m,d)
        d.loc[0,'sum_squared_error']=.6
        with self.assertRaises(ValueError):reconcile_daily(m,d)

    def test_equal_counts_do_not_hide_label_difference(self):
        a=pd.DataFrame({'threshold':Q,'n':[100]*7,'prevalence':[.1]*7})
        b=a.copy();compare_cohort(a,b)
        b.loc[2,'prevalence']=.2
        with self.assertRaises(ValueError):compare_cohort(a,b)

    def test_concatenated_export_parser_preserves_model_blocks(self):
        meta={'feature_mode':'calendar_risk_v2','train_fraction':.15}
        header='threshold,n,prevalence,brier,model,cutoff_kind'
        text=json.dumps(meta)+'\n'+header+'\n1,100,0.1,0.05,gbt,default_0.5\n'+header+'\n1,100,0.1,0.06,random_forest,default_0.5\n'
        m,frame=parse_export(text)
        self.assertEqual(set(frame.model),{'gbt','random_forest'})
        with self.assertRaises(ValueError):parse_export(text+header+'\n1,100,0.1,0.05,gbt,default_0.5\n')

    def test_archive_traversal_rejected(self):
        with self.assertRaises(ValueError):safe_target(Path('/tmp/import-root'),'../../bad')


if __name__=='__main__':unittest.main()
